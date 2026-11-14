"""``/api/memory`` – Erinnerungen (Phase 2).

Der Nutzer hat volle Kontrolle über sein Gedächtnis: einsehen, durchsuchen,
bearbeiten, löschen.  Keine versteckte Speicherung – Quelle (``source``) und
Herkunft (``source_ref``) sind in jeder Erinnerung sichtbar.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api import deps
from app.core.exceptions import ZenjiError
from app.database.models import MEMORY_STATUSES, MEMORY_TYPES
from app.engines.memory_engine import MemoryEngine
from app.schemas.memory import (
    MemoryCreate,
    MemoryOut,
    MemorySearchRequest,
    MemorySearchResult,
    MemoryStats,
    MemoryUpdate,
)

router = APIRouter(prefix="/memory", tags=["memory"])


def _db_session(request: Request):
    database = deps.get_database(request)
    with database.session() as session:
        yield session


class MemoryListResponse(BaseModel):
    """Liste + Zähler (transparent, für das Control Center)."""

    model_config = {"protected_namespaces": ()}

    memories: list[MemoryOut]
    stats: MemoryStats


@router.get("", summary="Erinnerungen auflisten (neueste zuerst) inkl. Zähler")
def list_memories(
    request: Request,
    memory_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    status_filter: str = Query(default="active", alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    session: Session = Depends(_db_session),
    engine: MemoryEngine = Depends(deps.get_memory_engine),
) -> MemoryListResponse:
    if memory_type and memory_type not in MEMORY_TYPES:
        raise HTTPException(
            status_code=422, detail={"code": "VALIDATION_ERROR", "message": f"Unbekannter Typ '{memory_type}'."}
        )
    if status_filter not in MEMORY_STATUSES:
        raise HTTPException(
            status_code=422, detail={"code": "VALIDATION_ERROR", "message": f"Unbekannter Status '{status_filter}'."}
        )
    memories = engine.list(
        session,
        memory_type=memory_type,
        category=category,
        status=status_filter,
        limit=limit,
    )
    stats = engine.stats(session)
    return MemoryListResponse(
        memories=[MemoryOut.model_validate(memory) for memory in memories],
        stats=MemoryStats(
            total=stats["total"],  # type: ignore[arg-type]
            active=stats["active"],  # type: ignore[arg-type]
            superseded=stats["superseded"],  # type: ignore[arg-type]
            archived=stats["archived"],  # type: ignore[arg-type]
            by_type=dict(stats["by_type"]),  # type: ignore[arg-type]
            categories=engine.categories(session),
            search_provider=str(stats["search_provider"]),
        ),
    )


@router.post("", status_code=status.HTTP_201_CREATED, summary="Erinnerung anlegen")
def create_memory(
    payload: MemoryCreate,
    session: Session = Depends(_db_session),
    engine: MemoryEngine = Depends(deps.get_memory_engine),
) -> MemoryOut:
    try:
        # API kennt nur Quelle 'user' – Chat-Speicherung erfolgt über den Core.
        memory, _merged = engine.create(
            session,
            content=payload.content,
            category=payload.category,
            memory_type=payload.memory_type,
            source="user",
            relevance=payload.relevance,
        )
    except ZenjiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return MemoryOut.model_validate(memory)


@router.post("/search", summary="Erinnerungen durchsuchen (FTS5/LIKE)")
def search_memories(
    payload: MemorySearchRequest,
    session: Session = Depends(_db_session),
    engine: MemoryEngine = Depends(deps.get_memory_engine),
) -> list[MemorySearchResult]:
    results = engine.search(
        session,
        payload.query,
        memory_type=payload.memory_type,
        category=payload.category,
        limit=payload.limit,
    )
    return [
        MemorySearchResult(memory=MemoryOut.model_validate(memory), score=score)
        for memory, score in results
    ]


@router.get("/{memory_id}", summary="Eine Erinnerung")
def get_memory(
    memory_id: str,
    session: Session = Depends(_db_session),
    engine: MemoryEngine = Depends(deps.get_memory_engine),
) -> MemoryOut:
    try:
        memory = engine.get(session, memory_id)
    except ZenjiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return MemoryOut.model_validate(memory)


@router.patch("/{memory_id}", summary="Erinnerung bearbeiten")
def update_memory(
    memory_id: str,
    payload: MemoryUpdate,
    session: Session = Depends(_db_session),
    engine: MemoryEngine = Depends(deps.get_memory_engine),
) -> MemoryOut:
    try:
        memory = engine.update(
            session, memory_id, payload.model_dump(exclude_unset=True)
        )
    except ZenjiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return MemoryOut.model_validate(memory)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Erinnerung löschen")
def delete_memory(
    memory_id: str,
    session: Session = Depends(_db_session),
    engine: MemoryEngine = Depends(deps.get_memory_engine),
) -> None:
    try:
        engine.delete(session, memory_id)
    except ZenjiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
