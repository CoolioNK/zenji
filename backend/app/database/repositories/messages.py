"""Repository für Nachrichten."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import MessageModel, ROLES, touch, utcnow


class MessageRepository:
    """Anhängen und Auslesen von Nachrichten, sortiert nach Erstellungszeit."""

    def add(
        self,
        session: Session,
        conversation_id: str,
        role: str,
        content: str,
    ) -> MessageModel:
        if role not in ROLES:
            raise ValueError(f"Unbekannte Rolle '{role}'. Erlaubt: {ROLES}")
        message = MessageModel(
            conversation_id=conversation_id,
            role=role,
            content=content,
            created_at=utcnow(),
        )
        session.add(message)
        session.flush()
        return message

    def history(
        self,
        session: Session,
        conversation_id: str,
        limit: int = 50,
        exclude_ids: set[str] | None = None,
    ) -> list[MessageModel]:
        """Letzte ``limit`` Nachrichten in chronologischer Reihenfolge.

        ``exclude_ids`` blendet soeben persistierte Nachrichten aus (sie
        werden separat als aktuelle Anfrage angehängt).
        """
        stmt = (
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.created_at.desc(), MessageModel.id.desc())
            .limit(limit)
        )
        if exclude_ids:
            stmt = stmt.where(MessageModel.id.not_in(exclude_ids))
        rows = list(session.scalars(stmt))
        rows.reverse()
        return rows

    def by_conversation(self, session: Session, conversation_id: str) -> list[MessageModel]:
        stmt = (
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.created_at.asc(), MessageModel.id.asc())
        )
        return list(session.scalars(stmt))

    @staticmethod
    def touch_conversation(session: Session, conversation) -> None:  # noqa: ANN001
        touch(conversation)
