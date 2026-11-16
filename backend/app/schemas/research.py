"""Schemata für ``/api/research`` (Recherche-Sessions)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResearchCreate(BaseModel):
    """Anfrage für ``POST /api/research`` (einzelner Durchlauf)."""

    model_config = ConfigDict(protected_namespaces=(), extra="forbid")

    question: str = Field(min_length=3, max_length=2000)
    mode: str = Field(default="standard", description="quick | standard | deep")

    @field_validator("mode")
    @classmethod
    def _validate_mode(cls, value: str | None) -> str:
        from app.web_intelligence.research_planner import normalize_mode

        normalized = normalize_mode(value)
        if normalized in ("", "off"):
            return "standard"
        return normalized


class ResearchSourceOut(BaseModel):
    """Quelle im Recherche-Report."""

    model_config = ConfigDict(protected_namespaces=())

    marker: int = 0
    id: str = ""
    title: str = ""
    url: str = ""
    domain: str = ""
    published_at: str | None = None
    source_type: str = "unbekannt"
    status: str = "ok"
    type_reason: str = ""
    freshness: str = ""
    age_days: int | None = None
    transparency: str = ""
    relevance: float = 0.0
    notes: list[str] = []


class ResearchFactOut(BaseModel):
    """Belegte Aussage mit Marker."""

    model_config = ConfigDict(protected_namespaces=())

    text: str
    marker: int
    source_id: str = ""
    source_type: str = "unbekannt"


class ResearchOut(BaseModel):
    """Kompakte Liste-/Erstellungsantwort (Session-Kopf)."""

    model_config = ConfigDict(protected_namespaces=())

    session_id: str | None = None
    question: str = ""
    mode: str = ""
    status: str = ""
    source_count: int = 0
    duration_ms: int | None = None
    created_at: str | None = None


class ResearchDetailOut(ResearchOut):
    """Voller Report (``GET /api/research/{id}``).

    Der gespeicherte Report-JSON wird unverändert als ``report`` geliefert –
    Nachvollziehbarkeit geht vor Schema-Zwang.
    """

    model_config = ConfigDict(protected_namespaces=())

    plan: dict = {}
    report: dict = {}
    queries: list[dict] = []
    citations: list[dict] = []
    error: str | None = None
