"""Schemata für ``/api/web`` (Suche, Einstellungen, Status)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WebSearchRequest(BaseModel):
    """Anfrage für ``POST /api/web/search``."""

    model_config = ConfigDict(protected_namespaces=(), extra="forbid")

    query: str = Field(min_length=1, max_length=400)
    provider: str | None = Field(default=None, description="searxng | brave (Default: Einstellung)")
    limit: int = Field(default=10, ge=1, le=25)

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normalized = value.strip().lower()
        if normalized not in ("searxng", "brave"):
            raise ValueError("provider muss 'searxng' oder 'brave' sein.")
        return normalized


class WebSearchHit(BaseModel):
    """Ein normalisiertes Suchergebnis."""

    model_config = ConfigDict(protected_namespaces=())

    title: str = ""
    url: str = ""
    domain: str = ""
    snippet: str = ""
    provider: str = ""
    rank: int = 0
    published_at: str | None = None


class WebSearchResponse(BaseModel):
    """Antwort für ``POST /api/web/search``."""

    model_config = ConfigDict(protected_namespaces=())

    query: str
    provider: str
    results: list[WebSearchHit]


class WebSettingsOut(BaseModel):
    """Nutzereinstellungen der Web Intelligence (Lesen).

    ``brave_api_key`` wird **niemals** zurückgegeben – nur der Hinweis,
    dass ein Schlüssel gesetzt ist.
    """

    model_config = ConfigDict(protected_namespaces=())

    provider: str
    searxng_url: str
    brave_api_key_set: bool
    language: str
    cache_ttl_s: float


class WebSettingsPatch(BaseModel):
    """Änderbare Einstellungen (``PATCH /api/web/settings``)."""

    model_config = ConfigDict(protected_namespaces=(), extra="forbid")

    provider: str | None = None
    searxng_url: str | None = None
    brave_api_key: str | None = None
    language: str | None = None
    cache_ttl_s: float | None = Field(default=None, ge=60.0, le=86_400.0)

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in ("searxng", "brave"):
            raise ValueError("provider muss 'searxng' oder 'brave' sein.")
        return normalized

    @field_validator("searxng_url")
    @classmethod
    def _validate_searxng_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped.startswith(("http://", "https://")):
            raise ValueError("searxng_url muss mit http:// oder https:// beginnen.")
        return stripped.rstrip("/")


class WebStatusOut(BaseModel):
    """Ehrlicher Betriebszustand der Web Intelligence."""

    model_config = ConfigDict(protected_namespaces=(), extra="allow")

    provider: str
    search: dict[str, Any]
    browser: dict[str, Any]
    cache: dict[str, Any]
    storage: dict[str, Any]
    planner_modes: list[str]
    version: str
