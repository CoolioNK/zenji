"""``/api/core`` – ZENJI-Core-Status und Kontext-Vorschau (Phase 2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app import __version__
from app.api import deps
from app.schemas.core import (
    ContextMessagePreview,
    ContextPreviewOut,
    ContextSectionOut,
    CoreStatusOut,
)
from app.services.settings_service import SettingsService
from app.services.zenji_core import ZenjiCore

router = APIRouter(prefix="/core", tags=["core"])


def _db_session(request: Request):
    database = deps.get_database(request)
    with database.session() as session:
        yield session


@router.get("/status", summary="Kern-Zustände: Persönlichkeit, Regeln, Gedächtnis, Modell")
def core_status(
    session: Session = Depends(_db_session),
    core: ZenjiCore = Depends(deps.get_zenji_core),
    settings_service: SettingsService = Depends(deps.get_settings_service),
) -> CoreStatusOut:
    settings = settings_service.effective(session)
    status = core.status(session, settings=settings)
    return CoreStatusOut(
        version=__version__,
        personality=status["personality"],  # type: ignore[arg-type]
        personality_id=status["personality_id"],  # type: ignore[arg-type]
        active_policies=status["active_policies"],  # type: ignore[arg-type]
        policy_conflicts=status["policy_conflicts"],  # type: ignore[arg-type]
        memories=dict(status["memories"]),  # type: ignore[arg-type]
        model=status["model"],  # type: ignore[str]
        provider=status["provider"],  # type: ignore[str]
        num_ctx=status["num_ctx"],  # type: ignore[arg-type]
        num_predict=status["num_predict"],  # type: ignore[arg-type]
    )


@router.get("/context-preview", summary="Nachvollziehbarer Kontext-Entwurf (ohne LLM-Aufruf)")
async def context_preview(
    message: str = Query(
        default="Was kannst du?",
        max_length=2000,
        description="Beispielnachricht, für die der Kontext kompiliert wird",
    ),
    conversation_id: str | None = Query(default=None),
    session: Session = Depends(_db_session),
    core: ZenjiCore = Depends(deps.get_zenji_core),
) -> ContextPreviewOut:
    preview = await core.context_preview(
        session, conversation_id=conversation_id, sample_message=message
    )
    return ContextPreviewOut(
        sections=[
            ContextSectionOut(
                key=section["key"],  # type: ignore[index]
                title=section["title"],  # type: ignore[index]
                tokens_est=section["tokens_est"],  # type: ignore[index]
                included=section["included"],  # type: ignore[index]
                truncated=section["truncated"],  # type: ignore[index]
                detail=section["detail"],  # type: ignore[index]
            )
            for section in preview["sections"]  # type: ignore[index]
        ],
        budget_tokens=preview["budget_tokens"],  # type: ignore[index]
        used_tokens=preview["used_tokens"],  # type: ignore[index]
        usage_ratio=preview["usage_ratio"],  # type: ignore[index]
        history_kept=preview["history_kept"],  # type: ignore[index]
        history_dropped=preview["history_dropped"],  # type: ignore[index]
        memories_kept=preview["memories_kept"],  # type: ignore[index]
        memories_dropped=preview["memories_dropped"],  # type: ignore[index]
        conflicts=preview["conflicts"],  # type: ignore[index]
        flags=preview["flags"],  # type: ignore[index]
        system_text=preview["system_text"],  # type: ignore[index]
        messages=[
            ContextMessagePreview(
                role=item["role"],  # type: ignore[index]
                content=item["content"],  # type: ignore[index]
                chars=item["chars"],  # type: ignore[index]
            )
            for item in preview["messages"]  # type: ignore[index]
        ],
        used_memory_ids=preview["used_memory_ids"],  # type: ignore[index]
    )
