"""Supabase-Authentifizierung für das ZENJI-Backend.

Aufgaben:

- **Token prüfen**: Das Frontend schickt nach dem Login den Supabase-Access-
  Token als ``Authorization: Bearer <token>``.  Das Backend verifiziert ihn
  über die Supabase-Auth-API (``GET /auth/v1/user``).  So braucht das Backend
  kein JWT-Secret und keine Service-Role-Keys im Browser.
- **Nutzer-Kontext setzen**: Die verifizierte Nutzer-ID wird in ein
  ``ContextVar`` geschrieben (siehe ``app.core.context``).  Der DB-Layer setzt
  daraus pro Transaktion ``request.jwt.claims`` – Postgres-RLS sorgt dann
  dafür, dass jeder Nutzer ausschließlich seine eigenen Zeilen sieht.
- **Profil anlegen + Defaults seeden**: Beim ersten Login wird ein
  ``profiles``-Eintrag erstellt und die Standard-Persönlichkeiten/-Regeln
  werden pro Nutzer angelegt.

Der Middleware-Modus ist nur aktiv, wenn Supabase konfiguriert ist
(``supabase_enabled``).  Ohne Konfiguration bleibt ZENJI im lokalen
Single-User-Modus (SQLite) – wichtig für Tests und Offline-Betrieb.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import Settings
from app.core.context import reset_current_user, set_current_user
from app.core.logging import get_logger
from app.database.database import Database
from app.database.models import ProfileModel

log = get_logger("auth")

#: Verifizierte Tokens werden kurz gecacht: jede Prüfung kostet einen HTTPS-
#: Roundtrip zur Supabase-Auth-API (auf dem Free-Tier mit 0.1 CPU plus
#: TLS-Handshake spürbar).  60 s sind sicherheitstechnisch harmlos – die
#: Access-Tokens laufen ohnehin nach ~1 Stunde ab.
_VERIFY_TTL = 60.0
_VERIFY_CACHE_MAX = 100

#: Pfade, die ohne Login erreichbar sind (Status/Modellinfo für die Login-Seite).
PUBLIC_PATHS = frozenset(
    {
        "/api/health",
        "/api/models",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/favicon.ico",
    }
)


class AuthError(Exception):
    """Ungültiger/fehlender Supabase-Token."""


@dataclass(slots=True)
class AuthUser:
    id: str
    email: str = ""


class SupabaseAuth:
    """Verifiziert Supabase-Access-Tokens über die Auth-API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: httpx.AsyncClient | None = None
        self._verified: dict[str, tuple[float, AuthUser]] = {}

    async def verify(self, token: str) -> AuthUser:
        if not self._settings.supabase_enabled:
            raise AuthError("Supabase ist nicht konfiguriert.")
        key = hashlib.sha256(token.encode("utf-8")).hexdigest()
        cached = self._verified.get(key)
        if cached is not None and time.monotonic() - cached[0] < _VERIFY_TTL:
            return cached[1]
        if len(self._verified) >= _VERIFY_CACHE_MAX:
            self._verified.clear()
        url = f"{self._settings.supabase_rest_url}/auth/v1/user"
        headers = {
            "apikey": self._settings.supabase_anon_key,
            "Authorization": f"Bearer {token}",
        }
        try:
            # Client wiederverwenden: pro Request ein neuer Client kostet
            # jedes Mal einen vollen TLS-Handshake (teuer auf schwacher CPU).
            if self._client is None:
                self._client = httpx.AsyncClient(timeout=10.0)
            response = await self._client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise AuthError(f"Supabase nicht erreichbar: {exc}") from exc
        if response.status_code != 200:
            raise AuthError("Token ungültig oder abgelaufen.")
        try:
            data = response.json()
        except ValueError as exc:
            raise AuthError("Ungültige Antwort der Supabase-Auth-API.") from exc
        user_id = str(data.get("id") or "").strip()
        if not user_id:
            raise AuthError("Antwort enthält keine Nutzer-ID.")
        user = AuthUser(id=user_id, email=str(data.get("email") or ""))
        self._verified[key] = (time.monotonic(), user)
        return user

    async def aclose(self) -> None:
        """HTTP-Client schließen (beim App-Down)."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._verified.clear()


class SupabaseAuthMiddleware:
    """Pure-ASGI-Middleware: verifiziert Token, setzt Nutzer-Kontext."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: Settings,
        database: Database,
        auth: SupabaseAuth | None = None,
    ) -> None:
        self.app = app
        self._settings = settings
        self._db = database
        self._auth = auth or SupabaseAuth(settings)
        self._initialized: set[str] = set()
        self._init_lock = asyncio.Lock()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or not self._settings.supabase_enabled:
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        method = str(scope.get("method", "GET")).upper()
        if method == "OPTIONS" or path in PUBLIC_PATHS or path.startswith("/docs"):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        authorization = headers.get("authorization", "")
        if not authorization.lower().startswith("bearer "):
            await self._unauthorized(send, "Kein Zugangstoken vorhanden.")
            return
        token = authorization[7:].strip()
        try:
            user = await self._auth.verify(token)
        except AuthError as exc:
            await self._unauthorized(send, str(exc))
            return

        tokens = set_current_user(user.id, user.email)
        try:
            await self._ensure_profile(user)
            await self.app(scope, receive, send)
        finally:
            reset_current_user(tokens)

    async def _ensure_profile(self, user: AuthUser) -> None:
        if user.id in self._initialized:
            return
        async with self._init_lock:
            if user.id in self._initialized:
                return
            try:
                await asyncio.to_thread(self._ensure_profile_sync, user)
                self._initialized.add(user.id)
            except Exception as exc:  # noqa: BLE001 – Login nicht blockieren
                log.exception("Profil/Seed für Nutzer %s fehlgeschlagen: %s", user.id, exc)

    def _ensure_profile_sync(self, user: AuthUser) -> None:
        with self._db.session() as session:
            profile = session.get(ProfileModel, user.id)
            if profile is None:
                session.add(ProfileModel(id=user.id, email=user.email))
                session.flush()
                self._seed_defaults(session)

    @staticmethod
    def _seed_defaults(session: Session) -> None:
        # Import lokal, um Zyklen mit main.py zu vermeiden.
        from app.database.migrations import _maybe_activate_zenji, _seed_policies, _seed_personalities

        _seed_personalities(session)
        _seed_policies(session)
        _maybe_activate_zenji(session)

    @staticmethod
    async def _unauthorized(send: Send, message: str) -> None:
        body = (
            b'{"error":{"code":"UNAUTHORIZED","message":"'
            + message.replace('"', "'").encode("utf-8")
            + b'"}}'
        )
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


__all__ = ["AuthError", "AuthUser", "PUBLIC_PATHS", "SupabaseAuth", "SupabaseAuthMiddleware"]