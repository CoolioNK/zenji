"""Repository für Web Intelligence: Recherchen, Quellen, Zitate, Cache.

Speicherbegrenzung ist eingebaut:

- **Ein** Snapshot je Quelle (Upsert statt History).
- ``enforce_limits`` löscht älteste Recherche-Sessions/Quellen/Cache-Einträge
  über konfigurierbare Maxima hinaus.
- ``purge_expired_cache`` entfernt abgelaufene Cache-Einträge.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.database.models import (
    CitationModel,
    ResearchCacheModel,
    ResearchSessionModel,
    SearchQueryModel,
    SearchResultModel,
    SourceModel,
    SourceSnapshotModel,
    new_id,
    utcnow,
)

#: Speichergrenzen (Verhindert unbegrenztes Wachstum der Datenbank).
MAX_SESSIONS = 100
MAX_SOURCES = 500
MAX_CACHE_ROWS = 500
#: Standard-TTL des Research Cache.
DEFAULT_CACHE_TTL_S = 3600.0


def _dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def _aware(value: datetime) -> datetime:
    """SQLite liest DateTime naive zurück – konsequent als UTC interpretieren."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class WebRepository:
    """Persistenzschicht der Web Intelligence Engine."""

    name = "web_repository"

    # --- Research Sessions ------------------------------------------------------------

    def create_session(
        self,
        session: Session,
        *,
        question: str,
        mode: str,
        plan: dict[str, Any],
    ) -> ResearchSessionModel:
        record = ResearchSessionModel(
            id=new_id(),
            question=question,
            mode=mode,
            status="running",
            plan_json=_dump(plan),
        )
        session.add(record)
        session.flush()
        return record

    def finish_session(
        self,
        session: Session,
        record: ResearchSessionModel,
        *,
        status: str,
        report: dict[str, Any] | None = None,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> ResearchSessionModel:
        record.status = status
        record.report_json = _dump(report or {})
        record.error = error
        record.duration_ms = duration_ms
        record.finished_at = utcnow()
        session.flush()
        return record

    def set_source_count(
        self, session: Session, record: ResearchSessionModel, count: int
    ) -> None:
        record.source_count = max(0, int(count))
        session.flush()

    def get_session(self, session: Session, session_id: str) -> ResearchSessionModel | None:
        return session.get(ResearchSessionModel, session_id)

    def list_sessions(
        self, session: Session, *, limit: int = 50
    ) -> list[ResearchSessionModel]:
        stmt = (
            select(ResearchSessionModel)
            .order_by(ResearchSessionModel.created_at.desc())
            .limit(limit)
        )
        return list(session.scalars(stmt))

    def delete_session(self, session: Session, session_id: str) -> bool:
        record = self.get_session(session, session_id)
        if record is None:
            return False
        session.delete(record)
        session.flush()
        return True

    # --- Suchanfragen & -ergebnisse ------------------------------------------------------

    def add_query(
        self,
        session: Session,
        *,
        research_session_id: str,
        query: str,
        provider: str,
        result_count: int,
    ) -> SearchQueryModel:
        record = SearchQueryModel(
            id=new_id(),
            session_id=research_session_id,
            query=query,
            provider=provider,
            result_count=max(0, int(result_count)),
        )
        session.add(record)
        session.flush()
        return record

    def add_results(
        self,
        session: Session,
        *,
        query_id: str,
        research_session_id: str,
        results: list[dict[str, Any]],
    ) -> int:
        for index, result in enumerate(results):
            published = result.get("published_at")
            session.add(
                SearchResultModel(
                    id=new_id(),
                    query_id=query_id,
                    session_id=research_session_id,
                    url=str(result.get("url", "")),
                    domain=str(result.get("domain", ""))[:255],
                    title=str(result.get("title", "")),
                    snippet=str(result.get("snippet", "")),
                    published_at=published if isinstance(published, datetime) else None,
                    rank=int(result.get("rank", index + 1)),
                )
            )
        session.flush()
        return len(results)

    def queries_of_session(
        self, session: Session, research_session_id: str
    ) -> list[SearchQueryModel]:
        stmt = (
            select(SearchQueryModel)
            .where(SearchQueryModel.session_id == research_session_id)
            .order_by(SearchQueryModel.created_at)
        )
        return list(session.scalars(stmt))

    # --- Quellen ------------------------------------------------------------------------

    def upsert_source(
        self,
        session: Session,
        *,
        original_url: str,
        canonical_url: str,
        domain: str,
        title: str,
        fetched_at: datetime,
        content_hash_value: str = "",
        http_status: int = 200,
        status: str = "ok",
        source_type: str = "unbekannt",
        content_chars: int = 0,
        author: str | None = None,
        published_at: datetime | None = None,
        quality: dict[str, Any] | None = None,
    ) -> tuple[SourceModel, bool]:
        """Legt die Quelle an oder aktualisiert die bestehende (Canonical-Dedupe)."""
        existing = session.scalars(
            select(SourceModel).where(SourceModel.canonical_url == canonical_url).limit(1)
        ).first()
        if existing is not None:
            existing.original_url = original_url or existing.original_url
            existing.title = title or existing.title
            existing.author = author or existing.author
            existing.published_at = published_at or existing.published_at
            existing.fetched_at = fetched_at
            existing.content_hash = content_hash_value or existing.content_hash
            existing.http_status = http_status or existing.http_status
            existing.status = status
            existing.source_type = source_type
            existing.content_chars = content_chars or existing.content_chars
            existing.quality_json = _dump(quality or {})
            existing.updated_at = utcnow()
            session.flush()
            return existing, False
        record = SourceModel(
            id=new_id(),
            original_url=original_url,
            canonical_url=canonical_url,
            domain=domain,
            title=title,
            author=author,
            published_at=published_at,
            fetched_at=fetched_at,
            content_hash=content_hash_value,
            http_status=http_status,
            status=status,
            source_type=source_type,
            content_chars=content_chars,
            quality_json=_dump(quality or {}),
        )
        session.add(record)
        session.flush()
        return record, True

    def get_source(self, session: Session, source_id: str) -> SourceModel | None:
        return session.get(SourceModel, source_id)

    def list_sources(
        self,
        session: Session,
        *,
        domain: str | None = None,
        source_type: str | None = None,
        limit: int = 200,
    ) -> list[SourceModel]:
        stmt = select(SourceModel).order_by(SourceModel.fetched_at.desc()).limit(limit)
        if domain:
            stmt = stmt.where(SourceModel.domain == domain)
        if source_type:
            stmt = stmt.where(SourceModel.source_type == source_type)
        return list(session.scalars(stmt))

    def delete_source(self, session: Session, source_id: str) -> bool:
        record = self.get_source(session, source_id)
        if record is None:
            return False
        session.delete(record)
        session.flush()
        return True

    def source_count(self, session: Session) -> int:
        return int(session.execute(select(func.count(SourceModel.id))).scalar() or 0)

    # --- Snapshots ------------------------------------------------------------------------

    def save_snapshot(
        self,
        session: Session,
        *,
        source_id: str,
        content: str,
        content_hash_value: str,
        extractor: str,
    ) -> SourceSnapshotModel:
        """Upsert: **ein** Snapshot je Quelle (Speicherbegrenzung)."""
        existing = session.scalars(
            select(SourceSnapshotModel)
            .where(SourceSnapshotModel.source_id == source_id)
            .limit(1)
        ).first()
        if existing is not None:
            existing.content = content
            existing.content_hash = content_hash_value
            existing.extractor = extractor
            existing.char_count = len(content)
            existing.extracted_at = utcnow()
            session.flush()
            return existing
        record = SourceSnapshotModel(
            id=new_id(),
            source_id=source_id,
            content=content,
            content_hash=content_hash_value,
            extractor=extractor,
            char_count=len(content),
        )
        session.add(record)
        session.flush()
        return record

    def get_snapshot(self, session: Session, source_id: str) -> SourceSnapshotModel | None:
        return session.scalars(
            select(SourceSnapshotModel)
            .where(SourceSnapshotModel.source_id == source_id)
            .limit(1)
        ).first()

    # --- Zitate -----------------------------------------------------------------------------

    def add_citations(
        self,
        session: Session,
        *,
        research_session_id: str,
        citations: list[dict[str, Any]],
    ) -> int:
        for entry in citations:
            session.add(
                CitationModel(
                    id=new_id(),
                    session_id=research_session_id,
                    source_id=str(entry.get("source_id", "")),
                    statement=str(entry.get("statement", "")),
                    marker=str(entry.get("marker", "")),
                )
            )
        session.flush()
        return len(citations)

    def citations_of_session(
        self, session: Session, research_session_id: str
    ) -> list[CitationModel]:
        stmt = (
            select(CitationModel)
            .where(CitationModel.session_id == research_session_id)
            .order_by(CitationModel.created_at)
        )
        return list(session.scalars(stmt))

    # --- Research Cache ----------------------------------------------------------------------

    def cache_get(self, session: Session, cache_key: str) -> Any | None:
        """Liefert den Cache-Payload, falls vorhanden und **nicht abgelaufen**."""
        record = session.scalars(
            select(ResearchCacheModel).where(ResearchCacheModel.cache_key == cache_key).limit(1)
        ).first()
        if record is None:
            return None
        if _aware(record.expires_at) <= utcnow():
            session.delete(record)
            session.flush()
            return None
        try:
            return json.loads(record.payload or "{}")
        except ValueError:
            return None

    def cache_set(
        self,
        session: Session,
        *,
        cache_key: str,
        kind: str,
        payload: Any,
        content_hash_value: str = "",
        ttl_s: float = DEFAULT_CACHE_TTL_S,
    ) -> ResearchCacheModel:
        existing = session.scalars(
            select(ResearchCacheModel).where(ResearchCacheModel.cache_key == cache_key).limit(1)
        ).first()
        now = utcnow()
        if existing is not None:
            existing.kind = kind
            existing.payload = _dump(payload)
            existing.content_hash = content_hash_value
            existing.created_at = now
            existing.expires_at = now + timedelta(seconds=ttl_s)
            session.flush()
            return existing
        record = ResearchCacheModel(
            id=new_id(),
            cache_key=cache_key[:128],
            kind=kind,
            payload=_dump(payload),
            content_hash=content_hash_value,
            expires_at=now + timedelta(seconds=ttl_s),
        )
        session.add(record)
        session.flush()
        return record

    def purge_expired_cache(self, session: Session) -> int:
        result = session.execute(
            delete(ResearchCacheModel).where(ResearchCacheModel.expires_at <= utcnow())
        )
        session.flush()
        return int(result.rowcount or 0)

    def clear_cache(self, session: Session) -> int:
        result = session.execute(delete(ResearchCacheModel))
        session.flush()
        return int(result.rowcount or 0)

    def cache_stats(self, session: Session) -> dict[str, int]:
        total = int(
            session.execute(select(func.count(ResearchCacheModel.id))).scalar() or 0
        )
        return {"total": total}

    # --- Speicherbegrenzung ----------------------------------------------------------------

    def enforce_limits(
        self,
        session: Session,
        *,
        max_sessions: int = MAX_SESSIONS,
        max_sources: int = MAX_SOURCES,
        max_cache_rows: int = MAX_CACHE_ROWS,
    ) -> dict[str, int]:
        """Löscht älteste Einträge über den Maxima hinaus (beim Commit-Abschluss)."""
        removed: dict[str, int] = {}

        excess = self._count(session, ResearchSessionModel) - max_sessions
        if excess > 0:
            oldest = session.scalars(
                select(ResearchSessionModel.id)
                .order_by(ResearchSessionModel.created_at.asc())
                .limit(excess)
            ).all()
            if oldest:
                session.execute(
                    delete(ResearchSessionModel).where(
                        ResearchSessionModel.id.in_(oldest)
                    )
                )
                removed["sessions"] = len(oldest)

        excess = self._count(session, SourceModel) - max_sources
        if excess > 0:
            oldest = session.scalars(
                select(SourceModel.id).order_by(SourceModel.fetched_at.asc()).limit(excess)
            ).all()
            if oldest:
                session.execute(delete(SourceModel).where(SourceModel.id.in_(oldest)))
                removed["sources"] = len(oldest)

        excess = self._count(session, ResearchCacheModel) - max_cache_rows
        if excess > 0:
            oldest = session.scalars(
                select(ResearchCacheModel.id)
                .order_by(ResearchCacheModel.created_at.asc())
                .limit(excess)
            ).all()
            if oldest:
                session.execute(
                    delete(ResearchCacheModel).where(ResearchCacheModel.id.in_(oldest))
                )
                removed["cache"] = len(oldest)

        if removed:
            session.flush()
        return removed

    def storage_stats(self, session: Session) -> dict[str, int]:
        return {
            "research_sessions": self._count(session, ResearchSessionModel),
            "search_queries": self._count(session, SearchQueryModel),
            "search_results": self._count(session, SearchResultModel),
            "sources": self._count(session, SourceModel),
            "source_snapshots": self._count(session, SourceSnapshotModel),
            "citations": self._count(session, CitationModel),
            "cache_entries": self._count(session, ResearchCacheModel),
        }

    @staticmethod
    def _count(session: Session, model) -> int:  # noqa: ANN001
        return int(session.execute(select(func.count(model.id))).scalar() or 0)
