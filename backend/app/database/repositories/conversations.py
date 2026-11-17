"""Repository für Konversationen."""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.context import get_current_user_id
from app.database.models import ConversationModel, MessageModel, touch


class ConversationRepository:
    """CRUD für Konversationen. Liefert ORM-Modelle (Mapping macht die Services)."""

    def list_all(self, session: Session) -> list[ConversationModel]:
        stmt = (
            select(ConversationModel)
            .order_by(ConversationModel.updated_at.desc())
            .limit(500)
        )
        return list(session.scalars(stmt))

    def get(self, session: Session, conversation_id: str) -> ConversationModel | None:
        return session.get(ConversationModel, conversation_id)

    def create(self, session: Session, title: str) -> ConversationModel:
        conversation = ConversationModel(
            title=title.strip() or "Neue Konversation",
            user_id=get_current_user_id(),
        )
        session.add(conversation)
        session.flush()
        return conversation

    def rename(self, session: Session, conversation_id: str, title: str) -> ConversationModel:
        conversation = self.get(session, conversation_id)
        if conversation is None:
            return None  # type: ignore[return-value]
        conversation.title = title.strip() or conversation.title
        touch(conversation)
        session.flush()
        return conversation

    def touch(self, session: Session, conversation_id: str) -> None:
        session.execute(
            update(ConversationModel)
            .where(ConversationModel.id == conversation_id)
            .values(updated_at=func.now())
        )

    def delete(self, session: Session, conversation_id: str) -> bool:
        conversation = self.get(session, conversation_id)
        if conversation is None:
            return False
        session.delete(conversation)
        session.flush()
        return True

    def count_messages(self, session: Session, conversation_ids: list[str]) -> dict[str, int]:
        """Nachrichtenanzahl je Konversation (ein Query, kein N+1)."""
        if not conversation_ids:
            return {}
        stmt = (
            select(MessageModel.conversation_id, func.count(MessageModel.id))
            .where(MessageModel.conversation_id.in_(conversation_ids))
            .group_by(MessageModel.conversation_id)
        )
        return {cid: count for cid, count in session.execute(stmt)}
