"""``GET /api/models`` – verfügbare Modelle beim aktiven Provider."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request

from app.api import deps
from app.core.exceptions import ProviderConnectionError

router = APIRouter(tags=["models"])


@router.get("/models", summary="Verfügbare Modelle und aktives Modell")
async def list_models(request: Request) -> dict[str, Any]:
    """Liefert auch bei ausgefallenem Provider HTTP 200 mit ``available:
    false`` und einer klaren Meldung – ideal für die Statusleiste."""
    engine = deps.get_llm_engine(request)
    database = deps.get_database(request)
    settings_service = deps.get_settings_service(request)
    provider = engine.provider

    provider_status = await provider.status()
    active_model = None
    try:

        def _active_model() -> str | None:
            with database.session() as session:
                return settings_service.effective(session).llm.model

        # Sync-DB nie im Event-Loop (Cloud: Blockaden → Instanz-Restarts).
        active_model = await asyncio.to_thread(_active_model)
    except Exception:  # noqa: BLE001 – ohne DB: Bootstrap-Default anzeigen
        active_model = settings_service.defaults().llm.model

    if not provider_status.available:
        return {
            "provider": provider.name,
            "available": False,
            "message": provider_status.detail or f"{provider.name} nicht erreichbar.",
            "active_model": active_model,
            "models": [],
        }

    try:
        models = await engine.list_models()
    except ProviderConnectionError as exc:
        return {
            "provider": provider.name,
            "available": False,
            "message": exc.message,
            "active_model": active_model,
            "models": [],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "provider": provider.name,
            "available": False,
            "message": f"Modelliste nicht abrufbar: {exc.__class__.__name__}",
            "active_model": active_model,
            "models": [],
        }

    return {
        "provider": provider.name,
        "available": True,
        "message": f"{len(models)} Modelle verfügbar.",
        "active_model": active_model,
        "models": [
            {
                "name": m.name,
                "family": m.family,
                "parameter_size": m.parameter_size,
                "quantization": m.quantization,
                "size_bytes": m.size_bytes,
                "modified_at": m.modified_at.isoformat() if m.modified_at else None,
            }
            for m in models
        ],
    }
