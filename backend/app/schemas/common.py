"""Gemeinsame API-Schemata."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Einheitliches Fehlerformat aller Endpunkte."""

    error: ErrorBody


class ErrorBody(BaseModel):
    code: str
    message: str
    detail: dict[str, Any] | None = None


class PagedList(BaseModel):
    """Platzhalter für spätere Paginierung (Phase 1: komplette Listen)."""

    model_config = {"protected_namespaces": ()}

    total: int = Field(ge=0)
