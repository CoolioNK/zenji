"""Schemata für Chat-Anfragen, -Antworten und SSE-Ereignisse."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.conversation import MessageOut


class ChatRequest(BaseModel):
    """Anfrage für ``POST /api/chat`` und ``POST /api/chat/stream``.

    Ohne ``conversation_id`` wird automatisch eine neue Konversation
    angelegt (Titel aus dem ersten Nutzerwortlaut).
    """

    model_config = ConfigDict(protected_namespaces=(), extra="forbid")

    conversation_id: str | None = Field(default=None, description="UUID einer bestehenden Konversation")
    message: str = Field(min_length=1, max_length=32000)

    @field_validator("conversation_id")
    @classmethod
    def _validate_uuid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            uuid.UUID(value)
        except ValueError as exc:
            raise ValueError("conversation_id muss eine gültige UUID sein") from exc
        return value


class ChatResponse(BaseModel):
    """Antwort für ``POST /api/chat`` (nicht-streamend)."""

    model_config = ConfigDict(protected_namespaces=())

    conversation_id: str
    user_message: MessageOut
    assistant_message: MessageOut


class SSEPayload(BaseModel):
    """Inhalt eines SSE-``data``-Felds (freies Objekt, kein restriktives Schema)."""

    model_config = ConfigDict(protected_namespaces=(), extra="allow")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SSEPayload":
        return cls.model_validate(data)
