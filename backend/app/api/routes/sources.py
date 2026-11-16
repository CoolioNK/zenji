"""``/api/sources`` – Quellenverwaltung (Phase 3).

Der Nutzer hat volle Kontrolle über seine recherchierten Quellen: einsehen
(inkl. gespeichertem Snapshot), filtern, löschen.  Der Snapshot-Inhalt wird
nur auf explizite Anfrage einer Quelle ausgeliefert.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api import deps
from app.core.exceptions import ZenjiError
from app.database.models import SOURCE_TYPES
from app.schemas.sources import (
    SourceListResponse,
    SourceOut,
    SourceSnapshotOut,
)
from app.services.web_intelligence_service import WebIntelligenceService

router = APIRouter(prefix="/sources", tags=["sources"])


def _db_session(request: Request):
    database = deps.get_database(request)
    with database.session() as session:
        yield session


def _out(record) -> SourceOut:
    return SourceOut(
        id=record.id,
        original_url=record.original_url,
        canonical_url=record.canonical_url,
        domain=record.domain,
        title=record.title,
        author=record.author,
        published_at=record.published_at.isoformat() if record.published_at else None,
        fetched_at=record.fetched_at.isoformat() if record.fetched_at else None,
        content_hash=record.content_hash,
        http_status=record.http_status,
        status=record.status,
        source_type=record.source_type,
        content_chars=record.content_chars,
        created_at=record.created_at.isoformat() if record.created_at else None,
    )


def _require(session: Session, web: WebIntelligenceService, source_id: str):
    record = web.get_source(session, source_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "SOURCE_NOT_FOUND", "message": "Quelle nicht gefunden."},
        )
    return record


@router.get("", summary="Quellen auflisten (filterbar)")
def list_sources(
    domain: str | None = Query(default=None),
    source_type: str | None = Query(default=None, alias="type"),
    limit: int = Query(default=200, ge=1, le=500),
    session: Session = Depends(_db_session),
    web: WebIntelligenceService = Depends(deps.get_web_intelligence),
) -> SourceListResponse:
    if source_type and source_type not in SOURCE_TYPES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": f"Unbekannter Quelltyp '{source_type}'. Erlaubt: {SOURCE_TYPES}.",
            },
        )
    records = web.list_sources(session, domain=domain, source_type=source_type, limit=limit)
    total = len(records)
    return SourceListResponse(sources=[_out(record) for record in records], total=total)


@router.get("/{source_id}", summary="Eine Quelle")
def get_source(
    source_id: str,
    session: Session = Depends(_db_session),
    web: WebIntelligenceService = Depends(deps.get_web_intelligence),
) -> SourceOut:
    record = _require(session, web, source_id)
    return _out(record)


@router.get("/{source_id}/snapshot", summary="Gespeicherter Inhalt einer Quelle")
def get_snapshot(
    source_id: str,
    session: Session = Depends(_db_session),
    web: WebIntelligenceService = Depends(deps.get_web_intelligence),
) -> SourceSnapshotOut:
    record = _require(session, web, source_id)
    snapshot = web.snapshot(session, source_id)
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "SOURCE_NOT_FOUND",
                "message": "Kein Snapshot gespeichert (Quelle evtl. nur blockiert vermerkt).",
            },
        )
    return SourceSnapshotOut(
        source_id=source_id,
        content=snapshot.content,
        content_hash=snapshot.content_hash,
        extractor=snapshot.extractor,
        char_count=snapshot.char_count,
        extracted_at=snapshot.extracted_at.isoformat() if snapshot.extracted_at else None,
    )


@router.delete("/{source_id}", summary="Quelle löschen (inkl. Snapshot)")
def delete_source(
    source_id: str,
    session: Session = Depends(_db_session),
    web: WebIntelligenceService = Depends(deps.get_web_intelligence),
) -> dict:
    try:
        record = _require(session, web, source_id)
        deleted = web.delete_source(session, record.id)
    except ZenjiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return {"deleted": deleted, "id": source_id}
