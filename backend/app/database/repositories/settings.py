"""Repository für Laufzeit-Einstellungen (Schlüssel/Wert, JSON-codiert)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.database.models import SettingModel


class SettingsRepository:
    def get(self, session: Session, key: str) -> str | None:
        record = session.get(SettingModel, key)
        return record.value if record else None

    def set(self, session: Session, key: str, value: str) -> None:
        record = session.get(SettingModel, key)
        if record is None:
            session.add(SettingModel(key=key, value=value))
        else:
            record.value = value
        session.flush()
