"""Conversation-Service: Verwaltung mehrerer Chats."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import ConversationNotFoundError
from app.database.models import ConversationModel, MessageModel
from app.database.repositories.conversations import ConversationRepository
from app.database.repositories.messages import MessageRepository
from app.schemas.conversation import (
    ALLOWED_ROLES,
    ConversationOut,
    ConversationSummary,
    MessageOut,
)


class ConversationService:
    """CRUD für Konversationen; Mapping zu API-Schemata inklusive."""

    def __init__(self) -> None:
        self._conversations = ConversationRepository()
        self._messages = MessageRepository()

    # --- Lesen ------------------------------------------------------------------
    def list_conversations(self, session: Session) -> list[ConversationSummary]:
        conversations = self._conversations.list_all(session)
        counts = self._conversations.count_messages(session, [c.id for c in conversations])
        return [
            ConversationSummary(
                id=c.id,
                title=c.title,
                created_at=c.created_at,
                updated_at=c.updated_at,
                message_count=counts.get(c.id, 0),
            )
            for c in conversations
        ]

    def get_conversation(self, session: Session, conversation_id: str) -> ConversationOut:
        conversation = self._require(session, conversation_id)
        return self._to_detail(conversation)

    def messages_of(self, session: Session, conversation_id: str) -> list[MessageOut]:
        conversation = self._require(session, conversation_id)
        return [MessageOut.model_validate(m) for m in conversation.messages]

    # --- Schreiben ----------------------------------------------------------------
    def create(self, session: Session, title: str | None = None) -> ConversationOut:
        conversation = self._conversations.create(session, title or "Neue Konversation")
        return self._to_detail(conversation)

    def rename(self, session: Session, conversation_id: str, title: str) -> ConversationOut:
        conversation = self._conversations.rename(session, conversation_id, title)
        if conversation is None:
            raise ConversationNotFoundError(
                f"Konversation '{conversation_id}' existiert nicht."
            )
        return self._to_detail(conversation)

    def delete(self, session: Session, conversation_id: str) -> None:
        if not self._conversations.delete(session, conversation_id):
            raise ConversationNotFoundError(f"Konversation '{conversation_id}' existiert nicht.")

    # --- Interna (für ChatService) -----------------------------------------------------
    def add_message(
        self,
        session: Session,
        conversation_id: str,
        role: str,
        content: str,
        *,
        require_exists: bool = True,
    ) -> MessageModel:
        """Hängt eine Nachricht an und aktualisiert ``updated_at``."""
        if role not in ALLOWED_ROLES:
            raise ValueError(f"Unzulässige Rolle '{role}'.")
        if require_exists:
            self._require(session, conversation_id)
        message = self._messages.add(session, conversation_id, role, content)
        conversation = session.get(ConversationModel, conversation_id)
        if conversation is not None:
            self._messages.touch_conversation(session, conversation)
        return message

    def history(
        self, session: Session, conversation_id: str, limit: int = 50,
        exclude_ids: set[str] | None = None,
    ) -> list[MessageModel]:
        self._require(session, conversation_id)
        return self._messages.history(session, conversation_id, limit=limit, exclude_ids=exclude_ids)

    def title_for_first_message(self, message: str) -> str:
        """Ableitender Titel aus der ersten Nutzeranfrage."""
        words = " ".join(message.split())
        return (words[:47] + "…") if len(words) > 48 else words

    def _require(self, session: Session, conversation_id: str) -> ConversationModel:
        conversation = self._conversations.get(session, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(f"Konversation '{conversation_id}' existiert nicht.")
        return conversation

    @staticmethod
    def _to_detail(conversation: ConversationModel) -> ConversationOut:
        return ConversationOut(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=len(conversation.messages),
            messages=[MessageOut.model_validate(m) for m in conversation.messages],
        )
