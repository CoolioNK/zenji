"""SQLAlchemy-Modelle: Konversationen, Nachrichten, Einstellungen."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

if TYPE_CHECKING:  # pragma: no cover
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


ROLES = ("system", "user", "assistant")


class Base(DeclarativeBase):
    pass


class ConversationModel(Base):
    """Eine Chat-Konversation (mehrere Chats möglich)."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200), default="Neue Konversation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    messages: Mapped[list["MessageModel"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="MessageModel.created_at",
        lazy="selectin",
    )


class MessageModel(Base):
    """Eine einzelne Nachricht innerhalb einer Konversation."""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('system','user','assistant')", name="ck_message_role"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[ConversationModel] = relationship(back_populates="messages")


class SettingModel(Base):
    """Laufzeit-Einstellungen als Schlüssel/Wert-Speicher (JSON in Text)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


def touch(conversation: ConversationModel) -> None:
    """Aktualisiert ``updated_at`` explizit (SQLite setzt onupdate bei ORM-Flush)."""
    conversation.updated_at = utcnow()
