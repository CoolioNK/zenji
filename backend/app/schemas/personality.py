"""Schemata für Persönlichkeitsprofile (Phase 2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.database.models import PERSONALITY_BASES, RESPONSE_LENGTHS

_FLOAT_FIELDS = ("formality", "humor", "directness", "creativity")


class PersonalityOut(BaseModel):
    """Ein Profil in der API-Antwort."""

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    name: str = Field(min_length=1, max_length=80)
    identity: str
    base_personality: str = Field(pattern="^(neutral|professional|friendly|casual|custom)$")
    communication_style: str
    formality: float = Field(ge=0.0, le=1.0)
    humor: float = Field(ge=0.0, le=1.0)
    directness: float = Field(ge=0.0, le=1.0)
    creativity: float = Field(ge=0.0, le=1.0)
    response_length: str = Field(pattern="^(short|balanced|detailed)$")
    language: str = Field(max_length=40)
    situational_behavior: dict[str, str]
    is_system: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PersonalityCreate(BaseModel):
    """Anlegen eines eigenen Profils (Systemprofile nur über Seed)."""

    model_config = ConfigDict(protected_namespaces=(), extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    identity: str = Field(default="", max_length=2000)
    base_personality: str = Field(default="custom")
    communication_style: str = Field(default="", max_length=500)
    formality: float = Field(default=0.5, ge=0.0, le=1.0)
    humor: float = Field(default=0.2, ge=0.0, le=1.0)
    directness: float = Field(default=0.6, ge=0.0, le=1.0)
    creativity: float = Field(default=0.5, ge=0.0, le=1.0)
    response_length: str = Field(default="balanced")
    language: str = Field(default="auto", max_length=40)
    situational_behavior: dict[str, str] = Field(default_factory=dict)
    is_active: bool = False

    @field_validator("base_personality")
    @classmethod
    def _base(cls, value: str) -> str:
        if value not in PERSONALITY_BASES:
            raise ValueError(f"base_personality muss einer aus {PERSONALITY_BASES} sein.")
        return value

    @field_validator("response_length")
    @classmethod
    def _length(cls, value: str) -> str:
        if value not in RESPONSE_LENGTHS:
            raise ValueError(f"response_length muss einer aus {RESPONSE_LENGTHS} sein.")
        return value


class PersonalityUpdate(BaseModel):
    """Teilweise Änderung eines Profils (alle Felder optional)."""

    model_config = ConfigDict(protected_namespaces=(), extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=80)
    identity: str | None = Field(default=None, max_length=2000)
    base_personality: str | None = None
    communication_style: str | None = Field(default=None, max_length=500)
    formality: float | None = Field(default=None, ge=0.0, le=1.0)
    humor: float | None = Field(default=None, ge=0.0, le=1.0)
    directness: float | None = Field(default=None, ge=0.0, le=1.0)
    creativity: float | None = Field(default=None, ge=0.0, le=1.0)
    response_length: str | None = None
    language: str | None = Field(default=None, max_length=40)
    situational_behavior: dict[str, str] | None = None
    is_active: bool | None = None

    @field_validator("base_personality")
    @classmethod
    def _base(cls, value: str | None) -> str | None:
        if value is not None and value not in PERSONALITY_BASES:
            raise ValueError(f"base_personality muss einer aus {PERSONALITY_BASES} sein.")
        return value

    @field_validator("response_length")
    @classmethod
    def _length(cls, value: str | None) -> str | None:
        if value is not None and value not in RESPONSE_LENGTHS:
            raise ValueError(f"response_length muss einer aus {RESPONSE_LENGTHS} sein.")
        return value


class PersonalityPreview(BaseModel):
    """Kompilierte Persönlichkeit (Vorschau der Engine)."""

    model_config = ConfigDict(protected_namespaces=())

    name: str
    is_active: bool
    compiled_text: str
