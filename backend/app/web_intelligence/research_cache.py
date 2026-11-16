"""Research Cache – TTL-Cache für Suchergebnisse und Abrufe (Phase 3).

Speichert Suchergebnisse, Quellenmetadaten, Extraktionszeitpunkt und
Content-Hash mit **Ablaufdatum**.  Veraltete Einträge werden beim Lesen
verworfen (niemals als aktuell dargestellt) und können gelöscht werden
(Benutzerfunktion) bzw. laufen automatisch ab.

Cache-Dauer konfigurierbar (TTL in Sekunden, Standard 1 h).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from app.database.models import content_hash
from app.database.repositories.web import DEFAULT_CACHE_TTL_S, WebRepository


class ResearchCache:
    """Semantischer TTL-Cache über dem ``research_cache``-Repository."""

    name = "research_cache"

    def __init__(
        self, repository: WebRepository | None = None, *, ttl_s: float = DEFAULT_CACHE_TTL_S
    ) -> None:
        self.repository = repository or WebRepository()
        self.ttl_s = ttl_s

    # --- Schlüssel ------------------------------------------------------------------

    @staticmethod
    def key_search(query: str, provider: str) -> str:
        digest = hashlib.sha1(f"{provider}|{query.lower().strip()}".encode()).hexdigest()[:24]
        return f"search:{provider}:{digest}"

    @staticmethod
    def key_fetch(url: str) -> str:
        digest = hashlib.sha1(url.strip().lower().encode()).hexdigest()[:24]
        return f"fetch:{digest}"

    # --- Suchergebnisse ----------------------------------------------------------------

    def get_search(self, session: Session, query: str, provider: str) -> list[dict] | None:
        payload = self.repository.cache_get(session, self.key_search(query, provider))
        if payload is None:
            return None
        results = payload.get("results", []) if isinstance(payload, dict) else []
        return results if isinstance(results, list) else None

    def set_search(
        self,
        session: Session,
        *,
        query: str,
        provider: str,
        results: list[dict[str, Any]],
        ttl_s: float | None = None,
    ) -> None:
        self.repository.cache_set(
            session,
            cache_key=self.key_search(query, provider),
            kind="search",
            payload={"results": results, "query": query, "provider": provider},
            content_hash_value=content_hash(json.dumps(results, ensure_ascii=False)),
            ttl_s=ttl_s if ttl_s is not None else self.ttl_s,
        )

    # --- Seitenabrufe --------------------------------------------------------------------

    def get_fetch(self, session: Session, url: str) -> dict[str, Any] | None:
        payload = self.repository.cache_get(session, self.key_fetch(url))
        if payload is None or not isinstance(payload, dict):
            return None
        return payload

    def set_fetch(
        self,
        session: Session,
        *,
        url: str,
        content: dict[str, Any],
        content_hash_value: str,
        ttl_s: float | None = None,
    ) -> None:
        self.repository.cache_set(
            session,
            cache_key=self.key_fetch(url),
            kind="fetch",
            payload={"url": url, **content},
            content_hash_value=content_hash_value,
            ttl_s=ttl_s if ttl_s is not None else self.ttl_s,
        )

    # --- Verwaltung -----------------------------------------------------------------------

    def clear(self, session: Session) -> int:
        """Benutzeraktion: gesamten Cache löschen."""
        return self.repository.clear_cache(session)

    def purge_expired(self, session: Session) -> int:
        return self.repository.purge_expired_cache(session)

    def stats(self, session: Session) -> dict[str, int]:
        return self.repository.cache_stats(session)


__all__ = ["ResearchCache"]
