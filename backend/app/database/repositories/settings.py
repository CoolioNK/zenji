"""Repository für Laufzeit-Einstellungen (Schlüssel/Wert, JSON-codiert)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.context import get_current_user_id, scope_key
from app.database.models import SettingModel


class SettingsRepository:
    """Lesen/Schreiben pro Nutzer.

    Der Schlüssel wird pro Nutzer mit einem Namensraum versehen
    (``<user_id>:<key>``), damit mehrere Accounts denselben logischen
    Schlüssel (z. B. ``llm``) verwenden können, ohne sich zu kollidieren.
    Zusätzlich greift in Supabase RLS auf ``user_id``.
    """

    def get(self, session: Session, key: str) -> str | None:
        record = session.get(SettingModel, scope_key(key))
        return record.value if record else None

    def set(self, session: Session, key: str, value: str) -> None:
        scoped = scope_key(key)
        record = session.get(SettingModel, scoped)
        if record is None:
            session.add(SettingModel(key=scoped, value=value, user_id=get_current_user_id()))
        else:
            record.value = value
        session.flush()