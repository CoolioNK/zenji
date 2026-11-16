"""Source Manager – zentrale Quelleverwaltung (Phase 3).

Jede recherchierte Quelle ist eindeutig identifizierbar: Original-URL,
Canonical-URL, Titel, Domain, Autor, Veröffentlichungsdatum, Abrufdatum,
Inhalts-Hash, HTTP-Status und Quellenstatus.  Mehrere URLs derselben
Canonical-URL werden zu **einer** Quelle zusammengeführt (Updatch statt
Duplikat); die ursprüngliche URL bleibt für die Anzeige erhalten.

Der Snapshot (extrahierter Inhalt) wird als **ein** Eintrag je Quelle
gehalten (Upsert) – keine unbegrenzte Content-History.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.database.models import content_hash as model_content_hash
from app.database.repositories.web import WebRepository
from app.web_intelligence.browser_engine import FetchResult
from app.web_intelligence.content_extractor import ExtractedContent
from app.web_intelligence.search_engine import canonical_url, domain_of

SOURCE_STATUS_OK = "ok"
SOURCE_STATUS_TRUNCATED = "truncated"
SOURCE_STATUS_BLOCKED = "blocked"
SOURCE_STATUS_FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RegisteredSource:
    """Ergebnis der Quellregistrierung (benutzt von Research Engine/API)."""

    id: str
    original_url: str
    canonical_url: str
    domain: str
    title: str
    author: str | None
    published_at: datetime | None
    fetched_at: datetime
    content_hash: str
    http_status: int
    status: str
    source_type: str
    content_chars: int
    is_new: bool
    has_content: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "original_url": self.original_url,
            "canonical_url": self.canonical_url,
            "domain": self.domain,
            "title": self.title,
            "author": self.author,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "fetched_at": self.fetched_at.isoformat(),
            "content_hash": self.content_hash,
            "http_status": self.http_status,
            "status": self.status,
            "source_type": self.source_type,
            "content_chars": self.content_chars,
            "is_new": self.is_new,
            "has_content": self.has_content,
        }


class SourceManager:
    """Registriert Abrufe als Quellen (Canonical-Dedupe + Snapshot)."""

    name = "source_manager"

    def __init__(self, repository: WebRepository | None = None) -> None:
        self.repository = repository or WebRepository()

    def register_fetch(
        self,
        session: Session,
        *,
        result: FetchResult,
        content: ExtractedContent | None = None,
        canonical: str | None = None,
        source_type: str = "unbekannt",
    ) -> RegisteredSource:
        """Registriert/aktualisiert die Quelle eines Abrufs.

        ``canonical`` gewinnt vor Trafilatura-Canonical vor Final-URL.
        Status: ``ok`` bzw. ``truncated`` (Größenlimit).
        """
        resolved_canonical = canonical or (content.canonical_url if content else None) or result.final_url
        domain = domain_of(resolved_canonical) or domain_of(result.final_url)
        title = (content.title if content else "") or result.title or domain
        author = content.author if content else None
        published = content.published_at if content else None
        text = (content.text if content else "") or ""
        digest = model_content_hash(text) if text.strip() else ""

        model, created = self.repository.upsert_source(
            session,
            original_url=result.url,
            canonical_url=canonical_url(resolved_canonical),
            domain=domain,
            title=title,
            fetched_at=result.fetched_at,
            content_hash_value=digest,
            http_status=result.status,
            status=SOURCE_STATUS_TRUNCATED if result.truncated else SOURCE_STATUS_OK,
            source_type=source_type,
            content_chars=len(text),
            author=author,
            published_at=published,
        )
        if text.strip():
            self.repository.save_snapshot(
                session,
                source_id=model.id,
                content=text,
                content_hash_value=digest,
                extractor=content.extractor if content else "",
            )
        return RegisteredSource(
            id=model.id,
            original_url=model.original_url,
            canonical_url=model.canonical_url,
            domain=model.domain,
            title=model.title,
            author=model.author,
            published_at=model.published_at,
            fetched_at=model.fetched_at,
            content_hash=model.content_hash,
            http_status=model.http_status,
            status=model.status,
            source_type=model.source_type,
            content_chars=model.content_chars,
            is_new=created,
            has_content=bool(text.strip()),
        )

    # --- Lese-/Verwaltungszugriffe (API) -------------------------------------------------

    def get(self, session: Session, source_id: str):
        return self.repository.get_source(session, source_id)

    def list(
        self,
        session: Session,
        *,
        domain: str | None = None,
        source_type: str | None = None,
        limit: int = 200,
    ):
        return self.repository.list_sources(
            session, domain=domain, source_type=source_type, limit=limit
        )

    def delete(self, session: Session, source_id: str) -> bool:
        return self.repository.delete_source(session, source_id)

    def snapshot_text(self, session: Session, source_id: str) -> str | None:
        snapshot = self.repository.get_snapshot(session, source_id)
        return snapshot.content if snapshot else None

    def count(self, session: Session) -> int:
        return self.repository.source_count(session)


__all__ = [
    "RegisteredSource",
    "SourceManager",
    "SOURCE_STATUS_BLOCKED",
    "SOURCE_STATUS_FAILED",
    "SOURCE_STATUS_OK",
    "SOURCE_STATUS_TRUNCATED",
]
