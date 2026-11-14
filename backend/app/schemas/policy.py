"""Schemata für Verhaltensregeln (Policies, Phase 2)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.database.models import POLICY_SCOPES


class PolicyOut(BaseModel):
    """Eine Regel in der API-Antwort."""

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    name: str
    instruction: str
    priority: int = Field(ge=0, le=100)
    enabled: bool
    category: str
    scope: str
    source: str = Field(pattern="^(system|user)$")
    created_at: datetime
    updated_at: datetime


class PolicyCreate(BaseModel):
    """Anlegen einer Nutzerregel (Systemregeln nur über Seed)."""

    model_config = ConfigDict(protected_namespaces=(), extra="forbid")

    id: str | None = Field(default=None, max_length=64, description="optional, sonst Slug aus Name")
    name: str = Field(min_length=1, max_length=120)
    instruction: str = Field(min_length=1, max_length=4000)
    priority: int = Field(default=50, ge=0, le=100)
    enabled: bool = True
    category: str = Field(default="stil", max_length=40)
    scope: str = Field(default="global")

    @field_validator("scope")
    @classmethod
    def _scope(cls, value: str) -> str:
        if value not in POLICY_SCOPES:
            raise ValueError(f"scope muss einer aus {POLICY_SCOPES} sein.")
        return value


class PolicyUpdate(BaseModel):
    """Teilweise Änderung einer Nutzerregel."""

    model_config = ConfigDict(protected_namespaces=(), extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    instruction: str | None = Field(default=None, min_length=1, max_length=4000)
    priority: int | None = Field(default=None, ge=0, le=100)
    enabled: bool | None = None
    category: str | None = Field(default=None, max_length=40)
    scope: str | None = None

    @field_validator("scope")
    @classmethod
    def _scope(cls, value: str | None) -> str | None:
        if value is not None and value not in POLICY_SCOPES:
            raise ValueError(f"scope muss einer aus {POLICY_SCOPES} sein.")
        return value


class PolicyConflictOut(BaseModel):
    """Erkannter Regelkonflikt (transparent berichtet)."""

    model_config = ConfigDict(protected_namespaces=())

    winner_id: str
    winner_name: str
    dropped_id: str
    dropped_name: str
    similarity: float
    reason: str


class PoliciesResponse(BaseModel):
    """Regelliste inkl. Konfliktbericht und Zähler."""

    model_config = ConfigDict(protected_namespaces=())

    policies: list[PolicyOut]
    conflicts: list[PolicyConflictOut] = Field(default_factory=list)
    disabled_count: int = 0
