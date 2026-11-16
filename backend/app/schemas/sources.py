"""Schemata für ``/api/sources`` (Quellenverwaltung)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SourceOut(BaseModel):
    """Registrierte Quelle (Metadaten, ohne Snapshot-Inhalt)."""

    model_config = ConfigDict(protected_namespaces=())

    id: str
    original_url: str
    canonical_url: str
    domain: str
    title: str
    author: str | None = None
    published_at: str | None = None
    fetched_at: str | None = None
    content_hash: str = ""
    http_status: int = 0
    status: str = "ok"
    source_type: str = "unbekannt"
    content_chars: int = 0
    created_at: str | None = None


class SourceListResponse(BaseModel):
    """Antwort für ``GET /api/sources``."""

    model_config = ConfigDict(protected_namespaces=())

    total: int
    sources: list[SourceOut]


class SourceSnapshotOut(BaseModel):
    """Gespeicherter Inhaltssnapshot einer Quelle."""

    model_config = ConfigDict(protected_namespaces=())

    source_id: str
    content: str
    content_hash: str = ""
    extractor: str = ""
    char_count: int = 0
    extracted_at: str | None = None
