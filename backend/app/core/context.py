"""Nutzer-Kontext für die aktuelle Anfrage.

Der Hintergrund: ZENJI speichert alle Nutzerdaten in Supabase Postgres. Die
Trennung der Nutzer wird **nicht** im Python-Code durch unzählige ``WHERE
user_id = ...``-Klauseln erzwungen, sondern durch Row-Level-Security (RLS) in
Postgres.  Dazu setzt der ``Database``-Layer pro Transaktion die
Postgres-Variable ``request.jwt.claims`` auf die aktuelle Nutzer-ID; die
RLS-Policies vergleichen jede Zeile mit ``auth.uid()``.

Damit dieser Nutzer-Kontext in synchronen Services (ChatService, Engines,
Repos) verfügbar ist – auch in Hintergrund-Tasks beim Streaming – halten wir
ihn in einem ``ContextVar``.
"""

from __future__ import annotations

from contextvars import ContextVar

#: UUID des aktuell authentifizierten Supabase-Nutzers (oder None).
current_user_id: ContextVar[str | None] = ContextVar("zenji_current_user_id", default=None)

#: E-Mail des aktuellen Nutzers (nur informativ, nicht für Autorisierung).
current_user_email: ContextVar[str | None] = ContextVar("zenji_current_user_email", default=None)


def get_current_user_id() -> str | None:
    """Aktuelle Nutzer-ID oder ``None`` (lokaler Modus / Hintergrund)."""
    return current_user_id.get()


def set_current_user(user_id: str | None, email: str | None = None) -> tuple[object, object]:
    """Setzt den Nutzer-Kontext und liefert Reset-Handles zurück."""
    return current_user_id.set(user_id), current_user_email.set(email)


def reset_current_user(tokens: tuple[object, object]) -> None:
    current_user_id.reset(tokens[0])  # type: ignore[arg-type]
    current_user_email.reset(tokens[1])  # type: ignore[arg-type]


def scope_key(key: str) -> str:
    """Namensraum für Schlüssel (Settings, Cache) pro Nutzer.

    Im lokalen Modus (kein Nutzer) bleibt der Schlüssel unverändert – damit
    Tests und der Offline-Betrieb identisch funktionieren.  In Supabase wird
    die Nutzer-ID vorangestellt, sodass ``key`` global eindeutig bleibt und
    RLS trotzdem greift.
    """
    user_id = get_current_user_id()
    return f"{user_id}:{key}" if user_id else key


def scope_entity_id(entity_id: str) -> str:
    """Namensraum für feste Entity-IDs (z. B. Policy-Slugs) pro Nutzer."""
    user_id = get_current_user_id()
    return f"{user_id}:{entity_id}" if user_id else entity_id


__all__ = [
    "current_user_email",
    "current_user_id",
    "get_current_user_id",
    "reset_current_user",
    "scope_entity_id",
    "scope_key",
    "set_current_user",
]