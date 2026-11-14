"""Schemata für Erinnerungen (Memory, Phase 2)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.database.models import MEMORY_TYPES, MEMORY_STATUSES


class MemoryOut(BaseModel):
    """Eine Erinnerung in der API-Antwort."""

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    content: str
    category: str
    memory_type: str = Field(pattern="^(conversation|long_term|preference|project)$")
    source: str
    source_ref: str | None = None
    relevance: float = Field(ge=0.0, le=1.0)
    status: str = Field(pattern="^(active|superseded|archived)$")
    supersedes_id: str | None = None
    last_used_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class MemoryCreate(BaseModel):
    """Anlegen einer Erinnerung (API kennt nur Quelle 'user')."""

    model_config = ConfigDict(protected_namespaces=(), extra="forbid")

    content: str = Field(min_length=1, max_length=2000)
    category: str = Field(default="allgemein", max_length=40)
    memory_type: str = Field(default="long_term")
    relevance: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("memory_type")
    @classmethod
    def _type(cls, value: str) -> str:
        if value not in MEMORY_TYPES:
            raise ValueError(f"memory_type muss einer aus {MEMORY_TYPES} sein.")
        return value


class MemoryUpdate(BaseModel):
    """Teilweise Änderung einer Erinnerung."""

    model_config = ConfigDict(protected_namespaces=(), extra="forbid")

    content: str | None = Field(default=None, min_length=1, max_length=2000)
    category: str | None = Field(default=None, max_length=40)
    memory_type: str | None = None
    relevance: float | None = Field(default=None, ge=0.0, le=1.0)
    status: str | None = None

    @field_validator("memory_type")
    @classmethod
    def _type(cls, value: str | None) -> str | None:
        if value is not None and value not in MEMORY_TYPES:
            raise ValueError(f"memory_type muss einer aus {MEMORY_TYPES} sein.")
        return value

    @field_validator("status")
    @classmethod
    def _status(cls, value: str | None) -> str | None:
        if value is not None and value not in MEMORY_STATUSES:
            raise ValueError(f"status muss einer aus {MEMORY_STATUSES} sein.")
        return value


class MemorySearchRequest(BaseModel):
    """Anfrage für ``POST /api/memory/search``."""

    model_config = ConfigDict(protected_namespaces=(), extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    memory_type: str | None = None
    category: str | None = Field(default=None, max_length=40)
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("memory_type")
    @classmethod
    def _type(cls, value: str | None) -> str | None:
        if value is not None and value not in MEMORY_TYPES:
            raise ValueError(f"memory_type muss einer aus {MEMORY_TYPES} sein.")
        return value


class MemorySearchResult(BaseModel):
    """Ein Suchtreffer (Erinnerung + Score)."""

    model_config = ConfigDict(protected_namespaces=())

    memory: MemoryOut
    score: float = Field(ge=0.0)


class MemoryStats(BaseModel):
    """Zähler für Control Center und Core-Status."""

    model_config = ConfigDict(protected_namespaces=())

    total: int = 0
    active: int = 0
    superseded: int = 0
    archived: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    categories: list[tuple[str, int]] = Field(default_factory=list)
    search_provider: str = "like"
