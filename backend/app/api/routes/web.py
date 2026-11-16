"""``/api/web`` – Suche, Einstellungen und Status der Web Intelligence (Phase 3).

Sicherheit/Transparenz:

- ``GET /api/web/settings`` gibt den Brave-API-Schlüssel **niemals** zurück,
  nur ``brave_api_key_set``.
- ``GET /api/web/status`` meldet ehrliche Betriebszustände (Suchanbieter,
  httpx/Playwright, Cache, Speicher) – keine erfundenen „verbunden“-Werte.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api import deps
from app.core.exceptions import ZenjiError
from app.schemas.web import (
    WebSearchRequest,
    WebSearchResponse,
    WebSearchHit,
    WebSettingsOut,
    WebSettingsPatch,
    WebStatusOut,
)
from app.services.web_intelligence_service import WebIntelligenceService

router = APIRouter(prefix="/web", tags=["web"])


def get_web(request: Request) -> WebIntelligenceService:
    return deps.get_web_intelligence(request)


@router.post("/search", summary="Eine Websuche über den konfigurierten Anbieter")
async def search(
    payload: WebSearchRequest,
    web: WebIntelligenceService = Depends(get_web),
) -> WebSearchResponse:
    try:
        results = await web.search(
            payload.query, provider=payload.provider, limit=payload.limit
        )
    except ZenjiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    hits = [WebSearchHit.model_validate(result) for result in results]
    provider = hits[0].provider if hits else (payload.provider or web.get_config().provider)
    return WebSearchResponse(query=payload.query, provider=provider, results=hits)


@router.get("/settings", summary="Web-Einstellungen lesen (ohne API-Schlüssel)")
def read_settings(web: WebIntelligenceService = Depends(get_web)) -> WebSettingsOut:
    config = web.get_config()
    return WebSettingsOut(
        provider=config.provider,
        searxng_url=config.searxng_url,
        brave_api_key_set=bool(config.brave_api_key),
        language=config.language,
        cache_ttl_s=config.cache_ttl_s,
    )


@router.patch("/settings", summary="Web-Einstellungen ändern")
def patch_settings(
    payload: WebSettingsPatch,
    web: WebIntelligenceService = Depends(get_web),
) -> WebSettingsOut:
    fields = payload.model_dump(exclude_unset=True)
    # leerer brave_api_key-String = Schlüssel entfernen; None = unverändert.
    try:
        config = web.patch_config(fields)
    except ZenjiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return WebSettingsOut(
        provider=config.provider,
        searxng_url=config.searxng_url,
        brave_api_key_set=bool(config.brave_api_key),
        language=config.language,
        cache_ttl_s=config.cache_ttl_s,
    )


@router.get("/status", summary="Betriebszustand der Web Intelligence (ehrlich)")
async def web_status(web: WebIntelligenceService = Depends(get_web)) -> WebStatusOut:
    report = await web.status()
    return WebStatusOut.model_validate(report)


@router.delete("/cache", summary="Such- und Abruf-Cache vollständig leeren (Nutzerkontrolle)")
def clear_cache(web: WebIntelligenceService = Depends(get_web)) -> dict:
    try:
        deleted = web.clear_cache()
    except ZenjiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return {"deleted": deleted}
