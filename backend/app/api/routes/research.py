"""``/api/research`` – Recherche-Sessions (Phase 3).

- ``POST /api/research``: vollständiger Durchlauf (blockierend, JSON-Report).
- ``POST /api/research/stream``: derselbe Durchlauf als SSE – ``research``-
  Events beschreiben **tatsächlich ausgeführte** Schritte (Suchanfrage,
  Abruf, Vergleich), kein erfundener Fortschritt; Abbruch über Verbindungsende
  bzw. ``abort``-Event.
- ``GET /api/research`` / ``GET /api/research/{id}``: nachvollziehbare Historie.
- ``DELETE /api/research/{id}``: Nutzerkontrolle (löscht Session + Zitate).
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api import deps
from app.core.exceptions import ZenjiError
from app.schemas.research import (
    ResearchCreate,
    ResearchDetailOut,
    ResearchOut,
)
from app.services.web_intelligence_service import WebIntelligenceService

router = APIRouter(prefix="/research", tags=["research"])


def _db_session(request: Request):
    database = deps.get_database(request)
    with database.session() as session:
        yield session


def _out_from_record(record) -> ResearchOut:
    return ResearchOut(
        session_id=record.id,
        question=record.question,
        mode=record.mode,
        status=record.status,
        source_count=record.source_count,
        duration_ms=record.duration_ms,
        created_at=record.created_at.isoformat() if record.created_at else None,
    )


def _require(session: Session, web: WebIntelligenceService, research_id: str):
    record = web.get_session(session, research_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESEARCH_NOT_FOUND", "message": "Recherche nicht gefunden."},
        )
    return record


@router.post("", summary="Recherche durchführen (vollständiger Report)")
async def run_research(
    payload: ResearchCreate,
    web: WebIntelligenceService = Depends(deps.get_web_intelligence),
) -> dict:
    """Ein Durchlauf; der Report-Dict wird 1:1 zurückgegeben (Nachvollziehbarkeit)."""
    try:
        return await web.research(payload.question, mode=payload.mode)
    except ZenjiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


@router.post("/stream", summary="Recherche als SSE-Stream (echter Fortschritt)")
async def stream_research(
    payload: ResearchCreate,
    web: WebIntelligenceService = Depends(deps.get_web_intelligence),
):
    """SSE: ``start`` → ``research``* (geplante Suche, Treffer, Abrufe,
    Vergleich, Abschluss) → ``done`` (Report)."""
    abort_event = asyncio.Event()
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    def on_progress(event: dict) -> None:
        queue.put_nowait(_sse("research", event))

    async def _run() -> None:
        try:
            await queue.put(_sse("start", {
                "question": payload.question,
                "mode": payload.mode,
            }))
            report = await web.research(
                payload.question,
                mode=payload.mode,
                progress=on_progress,
                abort_event=abort_event,
            )
            await queue.put(_sse("done", {"report": report}))
        except Exception as exc:  # noqa: BLE001 – Stream darf nicht abreißen
            from app.core.logging import get_logger

            get_logger("research_stream").warning("Recherche-Stream fehlgeschlagen: %s", exc)
            code = getattr(exc, "code", "WEB_INTELLIGENCE_ERROR")
            await queue.put(_sse("error", {
                "code": code,
                "message": str(getattr(exc, "message", exc)),
            }))
        finally:
            await queue.put(None)

    async def _generator():
        task = asyncio.create_task(_run())
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=0.5)
                except TimeoutError:
                    continue
                if chunk is None:
                    break
                yield chunk
        except asyncio.CancelledError:
            abort_event.set()
            raise
        finally:
            abort_event.set()
            if not task.done():
                task.cancel()

    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("", summary="Recherche-Historie (neueste zuerst)")
def list_research(
    limit: int = Query(default=50, ge=1, le=100),
    session: Session = Depends(_db_session),
    web: WebIntelligenceService = Depends(deps.get_web_intelligence),
) -> list[ResearchOut]:
    records = web.list_sessions(session, limit=limit)
    return [_out_from_record(record) for record in records]


@router.get("/{research_id}", summary="Eine Recherche mit vollem Report")
def get_research(
    research_id: str,
    session: Session = Depends(_db_session),
    web: WebIntelligenceService = Depends(deps.get_web_intelligence),
) -> ResearchDetailOut:
    record = _require(session, web, research_id)
    import json as _json

    try:
        report = _json.loads(record.report_json or "{}")
    except ValueError:
        report = {}
    try:
        plan = _json.loads(record.plan_json or "{}")
    except ValueError:
        plan = {}
    queries = [
        {
            "query": query.query,
            "provider": query.provider,
            "result_count": query.result_count,
            "created_at": query.created_at.isoformat() if query.created_at else None,
        }
        for query in web.queries(session, research_id)
    ]
    citations = [
        {
            "statement": citation.statement,
            "marker": citation.marker,
            "source_id": citation.source_id,
        }
        for citation in web.citations(session, research_id)
    ]
    return ResearchDetailOut(
        **_out_from_record(record).model_dump(),
        plan=plan,
        report=report,
        queries=queries,
        citations=citations,
        error=record.error,
    )


@router.delete("/{research_id}", summary="Recherche löschen (inkl. Zitate)")
def delete_research(
    research_id: str,
    session: Session = Depends(_db_session),
    web: WebIntelligenceService = Depends(deps.get_web_intelligence),
) -> dict:
    record = _require(session, web, research_id)
    deleted = web.delete_session(session, record.id)
    return {"deleted": deleted, "id": research_id}


def _sse(event: str, data: dict) -> bytes:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")
