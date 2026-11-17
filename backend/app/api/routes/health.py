"""``GET /api/health`` – Gesamtstatus von ZENJI."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request

from app import __version__
from app.api import deps

router = APIRouter(tags=["health"])


@router.get("/health", summary="Status von Backend, SSD, Datenbank, Ollama und Modell")
async def health(request: Request) -> dict[str, Any]:
    """Nie 500: Der Health-Endpoint liefert auch im gestörten Zustand eine
    verständliche Struktur (``status: ok | degraded``) für das Frontend."""
    started = time.perf_counter()
    storage = deps.get_storage(request)
    database = deps.get_database(request)
    engine = deps.get_llm_engine(request)
    settings_service = deps.get_settings_service(request)
    settings = deps.get_settings(request)
    supabase_mode = settings.supabase_enabled

    storage_status = storage.status()
    if supabase_mode:
        storage_block = {
            "available": True,
            "root": "supabase",
            "message": "Cloud-Speicher (Supabase).",
        }
    else:
        storage_block = {
            "available": storage_status.available,
            "root": storage_status.root,
            "message": storage_status.message,
        }

    database_ok = database.is_ready()
    database_message = (
        "Datenbank verbunden." if database_ok else "Datenbank nicht erreichbar."
    )
    try:
        database_path = (
            "supabase" if database.engine.dialect.name == "postgresql" else str(database.db_path)
        )
    except Exception:  # noqa: BLE001 – Statusabfrage darf nicht crashen
        database_path = "unbekannt"

    provider_status = await engine.provider_status()
    model = None
    model_status: dict[str, Any] = {"model": None, "available": False, "message": ""}
    if provider_status.available:
        try:
            with database.session() as session:
                effective = settings_service.effective(session)
            model = effective.llm.model
            status = await engine.model_manager.status_for(model)
            model_status = {
                "model": status.model,
                "available": status.model_available,
                "message": status.message,
            }
        except Exception as exc:  # noqa: BLE001 – Health darf niemals crashen
            model_status["message"] = (
                f"Modellstatus nicht ermittelbar: {exc.__class__.__name__}"
            )

    storage_ok = storage_block["available"] or supabase_mode
    degraded = not (storage_ok and database_ok and provider_status.available)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

    return {
        "status": "degraded" if degraded else "ok",
        "version": __version__,
        "time_ms": elapsed_ms,
        "supabase": settings.supabase_enabled,
        "storage": storage_block,
        "database": {
            "ok": database_ok,
            "path": database_path,
            "message": database_message,
        },
        "ollama": {
            "available": provider_status.available,
            "version": provider_status.version,
            "base_url": engine.provider._base_url
            if hasattr(engine.provider, "_base_url")
            else None,
            "message": provider_status.detail or "",
            # Tatsächlicher aktiver Provider (z. B. "ollama" oder "cloudflare").
            "provider": engine.provider.name,
        },
        "model": model_status,
    }
