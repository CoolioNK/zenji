"""Schemata für den ZENJI Core (Status und Kontext-Preview, Phase 2)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CommunicationModeOut(BaseModel):
    """Ein verfügbarer Kommunikationsmodus (v0.3.0)."""

    model_config = ConfigDict(protected_namespaces=())

    key: str
    label: str


class CoreStatusOut(BaseModel):
    """``GET /api/core/status`` – zentrale Kern-Zustände."""

    model_config = ConfigDict(protected_namespaces=())

    version: str
    personality: str | None = None
    personality_id: str | None = None
    active_policies: int = Field(ge=0)
    policy_conflicts: int = Field(ge=0)
    memories: dict[str, object] = Field(default_factory=dict)
    model: str
    provider: str
    num_ctx: int
    num_predict: int
    communication_modes: list[CommunicationModeOut] = Field(default_factory=list)
    communication_default_mode: str = ""


class ContextSectionOut(BaseModel):
    """Ein Abschnitt des Kontextplans."""

    model_config = ConfigDict(protected_namespaces=())

    key: str
    title: str
    tokens_est: int
    included: bool = True
    truncated: bool = False
    detail: str = ""


class ContextMessagePreview(BaseModel):
    """Gekürzte Nachrichtenvorschau."""

    model_config = ConfigDict(protected_namespaces=())

    role: str
    content: str
    chars: int


class ContextPreviewOut(BaseModel):
    """``GET /api/core/context-preview`` – nachvollziehbarer Kontext-Entwurf."""

    model_config = ConfigDict(protected_namespaces=())

    sections: list[ContextSectionOut]
    budget_tokens: int
    used_tokens: int
    usage_ratio: float = Field(ge=0.0, le=1.0)
    history_kept: int
    history_dropped: int
    memories_kept: int
    memories_dropped: int
    conflicts: int
    flags: list[str] = Field(default_factory=list)
    system_text: str
    messages: list[ContextMessagePreview]
    used_memory_ids: list[str] = Field(default_factory=list)
    mode: str | None = None
