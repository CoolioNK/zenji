"""``GET /api/settings`` und ``PATCH /api/settings`` – Konfigurationssystem."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api import deps
from app.schemas.settings import SettingsOut, SettingsPatch
from app.services.settings_service import SettingsService

router = APIRouter(tags=["settings"])


def _db_session(request: Request):
    database = deps.get_database(request)
    with database.session() as session:
        yield session


@router.get("/settings", summary="Effektive Einstellungen (Laufzeit + Defaults)")
def get_settings(
    request: Request,
    session: Session = Depends(_db_session),
    settings_service: SettingsService = Depends(deps.get_settings_service),
) -> SettingsOut:
    return settings_service.effective(session)


@router.patch("/settings", summary="Einstellungen teilweise ändern (validiert, persistent)")
def patch_settings(
    patch: SettingsPatch,
    request: Request,
    session: Session = Depends(_db_session),
    settings_service: SettingsService = Depends(deps.get_settings_service),
) -> SettingsOut:
    """Deep-Merge je Gruppe (``llm``, ``providers.ollama``, ``persona``).
    Ungültige Werte führen zu HTTP 422 mit konkretem Feldhinweis."""
    return settings_service.patch(session, patch)
