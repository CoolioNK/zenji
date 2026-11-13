"""Konversations-Routen: mehrere Chats verwalten."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api import deps
from app.core.exceptions import ConversationNotFoundError
from app.schemas.conversation import (
    ConversationCreate,
    ConversationOut,
    ConversationSummary,
    ConversationUpdate,
)
from app.services.conversation_service import ConversationService

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _db_session(request: Request):
    database = deps.get_database(request)
    with database.session() as session:
        yield session


@router.get("", summary="Alle Konversationen (neueste zuerst)")
def list_conversations(
    session: Session = Depends(_db_session),
    service: ConversationService = Depends(deps.get_conversation_service),
) -> list[ConversationSummary]:
    return service.list_conversations(session)


@router.post("", status_code=status.HTTP_201_CREATED, summary="Neue Konversation anlegen")
def create_conversation(
    payload: ConversationCreate,
    session: Session = Depends(_db_session),
    service: ConversationService = Depends(deps.get_conversation_service),
) -> ConversationOut:
    return service.create(session, payload.title)


@router.get("/{conversation_id}", summary="Konversation mit allen Nachrichten")
def get_conversation(
    conversation_id: str,
    session: Session = Depends(_db_session),
    service: ConversationService = Depends(deps.get_conversation_service),
) -> ConversationOut:
    try:
        return service.get_conversation(session, conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": exc.code, "message": exc.message}) from exc


@router.patch("/{conversation_id}", summary="Konversation umbenennen")
def rename_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    session: Session = Depends(_db_session),
    service: ConversationService = Depends(deps.get_conversation_service),
) -> ConversationOut:
    try:
        return service.rename(session, conversation_id, payload.title)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": exc.code, "message": exc.message}) from exc


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Konversation löschen")
def delete_conversation(
    conversation_id: str,
    session: Session = Depends(_db_session),
    service: ConversationService = Depends(deps.get_conversation_service),
) -> None:
    try:
        service.delete(session, conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": exc.code, "message": exc.message}) from exc
