"""Schemata für Konversationen und Nachrichten."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

ROLE_SYSTEM = "system"
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ALLOWED_ROLES = (ROLE_SYSTEM, ROLE_USER, ROLE_ASSISTANT)


class MessageOut(BaseModel):
    """Eine gespeicherte Nachricht."""

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    conversation_id: str
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str
    created_at: datetime


class ConversationSummary(BaseModel):
    """Eintrag der Konversationsliste (Sidebar)."""

    model_config = ConfigDict(protected_namespaces=())

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class ConversationOut(ConversationSummary):
    """Konversation inkl. aller Nachrichten."""

    messages: list[MessageOut]


class ConversationCreate(BaseModel):
    """Neue Konversation anlegen (Titel optional)."""

    title: str | None = Field(default=None, max_length=200)


class ConversationUpdate(BaseModel):
    """Konversation umbenennen."""

    title: str = Field(min_length=1, max_length=200)
