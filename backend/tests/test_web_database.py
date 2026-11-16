"""Tests: Web Intelligence Datenbank-Layer (Phase 3) – Models, Repository,
Speicherbegrenzung, Cache-TTL."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.database.database import Database
from app.database.models import (
    CitationModel,
    ResearchCacheModel,
    SearchQueryModel,
    SearchResultModel,
    SourceModel,
    SourceSnapshotModel,
)
from app.database.repositories.web import (
    DEFAULT_CACHE_TTL_S,
    MAX_CACHE_ROWS,
    MAX_SESSIONS,
    MAX_SOURCES,
    WebRepository,
)

REPO = WebRepository()


def _db(tmp_path: Path) -> Database:
    settings = Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]
    db = Database(settings)
    db.create_schema()
    return db


# --- Research Sessions --------------------------------------------------------------------


def test_session_lifecycle(tmp_path):
    db = _db(tmp_path)
    with db.session() as session:
        record = REPO.create_session(
            session,
            question="Was ist die neueste Python-Version?",
            mode="quick",
            plan={"queries": ["python version"]},
        )
        research_id = record.id
        assert record.status == "running"
        REPO.set_source_count(session, record, 3)
        REPO.finish_session(
            session,
            record,
            status="done",
            report={"facts": []},
            duration_ms=1234,
        )

    with db.session() as session:
        loaded = REPO.get_session(session, research_id)
        assert loaded is not None
        assert loaded.status == "done"
        assert loaded.source_count == 3
        assert loaded.duration_ms == 1234
        assert loaded.finished_at is not None
        sessions = REPO.list_sessions(session)
        assert len(sessions) == 1


def test_session_delete_kaskadiert(tmp_path):
    db = _db(tmp_path)
    with db.session() as session:
        record = REPO.create_session(session, question="q", mode="quick", plan={})
        research_id = record.id
        REPO.add_query(
            session, research_session_id=research_id, query="x", provider="fake", result_count=1
        )
    with db.session() as session:
        assert REPO.delete_session(session, research_id) is True
        assert REPO.delete_session(session, research_id) is False
        assert list(session.scalars(select(SearchQueryModel))) == []


# --- Suchanfragen & Ergebnisse ---------------------------------------------------------------


def test_anfragen_und_ergebnisse_werden_gespeichert(tmp_path):
    db = _db(tmp_path)
    with db.session() as session:
        research = REPO.create_session(session, question="q", mode="standard", plan={})
        query = REPO.add_query(
            session, research_session_id=research.id, query="python 2026",
            provider="searxng", result_count=2,
        )
        REPO.add_results(
            session,
            query_id=query.id,
            research_session_id=research.id,
            results=[
                {"url": "https://a.example/1", "domain": "a.example", "title": "A",
                 "snippet": "s", "rank": 1},
                {"url": "https://b.example/2", "domain": "b.example", "title": "B",
                 "snippet": "t", "rank": 2,
                 "published_at": datetime(2026, 11, 1, tzinfo=UTC)},
            ],
        )

    with db.session() as session:
        results = list(session.scalars(select(SearchResultModel)))
        assert len(results) == 2
        dated = [r for r in results if r.published_at is not None]
        assert len(dated) == 1 and dated[0].published_at.year == 2026
        queries = REPO.queries_of_session(session, _research_id_of(session))
        assert queries[0].provider == "searxng"


def _research_id_of(session) -> str:
    from app.database.models import ResearchSessionModel

    return list(session.scalars(select(ResearchSessionModel)))[0].id


# --- Quellen & Snapshots ------------------------------------------------------------------------


def test_quellen_upsert_dedupe_ueber_canonical(tmp_path):
    db = _db(tmp_path)
    fetched = datetime.now(UTC)
    with db.session() as session:
        first, created = REPO.upsert_source(
            session,
            original_url="https://example.com/artikel?ref=x",
            canonical_url="https://example.com/artikel",
            domain="example.com",
            title="Artikel",
            fetched_at=fetched,
            status="ok",
            content_chars=500,
        )
        assert created is True

        # Zweite URL derselben Canonical-Quelle → Update, kein Duplikat:
        second, created = REPO.upsert_source(
            session,
            original_url="https://example.com/artikel?utm=mail",
            canonical_url="https://example.com/artikel",
            domain="example.com",
            title="Artikel (aktualisiert)",
            fetched_at=fetched,
        )
        assert created is False
        assert second.id == first.id

        # Andere Canonical-URL → eigene Quelle:
        third, created = REPO.upsert_source(
            session,
            original_url="https://anders.example/",
            canonical_url="https://anders.example/",
            domain="anders.example",
            title="Anders",
            fetched_at=fetched,
        )
        assert created is True
        assert third.id != first.id

    with db.session() as session:
        assert REPO.source_count(session) == 2


def test_snapshot_upsert_ersetzt_alten_inhalt(tmp_path):
    db = _db(tmp_path)
    with db.session() as session:
        source, _ = REPO.upsert_source(
            session,
            original_url="https://example.com/a",
            canonical_url="https://example.com/a",
            domain="example.com",
            title="A",
            fetched_at=datetime.now(UTC),
        )
        first = REPO.save_snapshot(
            session, source_id=source.id, content="alt " * 100,
            content_hash_value="h1", extractor="trafilatura",
        )
        second = REPO.save_snapshot(
            session, source_id=source.id, content="neu",
            content_hash_value="h2", extractor="beautifulsoup",
        )
        assert first.id == second.id
        snapshots = list(session.scalars(select(SourceSnapshotModel)))
        assert len(snapshots) == 1  # Upsert, keine History
        assert snapshots[0].content == "neu"
        assert snapshots[0].char_count == 3

    with db.session() as session:
        snapshot = REPO.get_snapshot(session, _source_id_of(session))
        assert snapshot is not None
        assert snapshot.extractor == "beautifulsoup"


def _source_id_of(session) -> str:
    return list(session.scalars(select(SourceModel)))[0].id


def test_quellen_loeschen_kaskadiert_snapshot(tmp_path):
    db = _db(tmp_path)
    with db.session() as session:
        source, _ = REPO.upsert_source(
            session,
            original_url="https://example.com/a",
            canonical_url="https://example.com/a",
            domain="example.com",
            title="A",
            fetched_at=datetime.now(UTC),
        )
        REPO.save_snapshot(
            session, source_id=source.id, content="x", content_hash_value="h", extractor="t"
        )
        source_id = source.id
    with db.session() as session:
        assert REPO.delete_source(session, source_id) is True
        assert list(session.scalars(select(SourceSnapshotModel))) == []


# --- Zitate --------------------------------------------------------------------------------------


def test_zitate_werden_pro_session_gespeichert(tmp_path):
    db = _db(tmp_path)
    with db.session() as session:
        research = REPO.create_session(session, question="q", mode="quick", plan={})
        source, _ = REPO.upsert_source(
            session,
            original_url="https://example.com/a",
            canonical_url="https://example.com/a",
            domain="example.com",
            title="A",
            fetched_at=datetime.now(UTC),
        )
        REPO.add_citations(
            session,
            research_session_id=research.id,
            citations=[
                {"source_id": source.id, "statement": "Python 3.14 ist aktuell.", "marker": "[1]"}
            ],
        )
    with db.session() as session:
        citations = list(session.scalars(select(CitationModel)))
        assert len(citations) == 1
        assert citations[0].marker == "[1]"


# --- Research Cache -------------------------------------------------------------------------------


def test_cache_set_get_und_ttl(tmp_path):
    db = _db(tmp_path)
    with db.session() as session:
        REPO.cache_set(
            session, cache_key="fetch:abc", kind="fetch",
            payload={"text": "Inhalt"}, content_hash_value="h", ttl_s=DEFAULT_CACHE_TTL_S,
        )
        payload = REPO.cache_get(session, "fetch:abc")
        assert payload == {"text": "Inhalt"}

        # Abgelaufener Eintrag → None (und wird entfernt):
        REPO.cache_set(
            session, cache_key="fetch:old", kind="fetch", payload={"x": 1}, ttl_s=-1.0
        )
        assert REPO.cache_get(session, "fetch:old") is None
        assert REPO.cache_get(session, "fetch:abc") == {"text": "Inhalt"}


def test_cache_purge_und_clear(tmp_path):
    db = _db(tmp_path)
    with db.session() as session:
        REPO.cache_set(session, cache_key="a", kind="fetch", payload={"a": 1}, ttl_s=-1.0)
        REPO.cache_set(session, cache_key="b", kind="search", payload={"b": 2})
        assert REPO.purge_expired_cache(session) == 1
        assert REPO.clear_cache(session) == 1
        assert REPO.cache_stats(session) == {"total": 0}


def test_cache_ersetzt_bestehenden_schluessel(tmp_path):
    db = _db(tmp_path)
    with db.session() as session:
        REPO.cache_set(session, cache_key="k", kind="fetch", payload={"v": 1})
        REPO.cache_set(session, cache_key="k", kind="fetch", payload={"v": 2})
        entries = list(session.scalars(select(ResearchCacheModel)))
        assert len(entries) == 1
        assert REPO.cache_get(session, "k") == {"v": 2}


# --- Speicherbegrenzung ------------------------------------------------------------------------------


def test_enforce_limits_loescht_aelteste(tmp_path):
    assert MAX_SESSIONS <= 200 and MAX_SOURCES <= 1000 and MAX_CACHE_ROWS <= 1000

    db = _db(tmp_path)
    with db.session() as session:
        for index in range(4):
            REPO.create_session(session, question=f"q{index}", mode="quick", plan={})
            REPO.upsert_source(
                session,
                original_url=f"https://d{index}.example/",
                canonical_url=f"https://d{index}.example/",
                domain=f"d{index}.example",
                title=f"T{index}",
                fetched_at=datetime.now(UTC) + timedelta(minutes=index),
            )
        removed = REPO.enforce_limits(session, max_sessions=2, max_sources=2, max_cache_rows=2)
        assert removed == {"sessions": 2, "sources": 2}
        stats = REPO.storage_stats(session)
        assert stats["research_sessions"] == 2
        assert stats["sources"] == 2


def test_storage_stats_zaehlt_alle_tabellen(tmp_path):
    db = _db(tmp_path)
    with db.session() as session:
        stats = REPO.storage_stats(session)
        assert set(stats) == {
            "research_sessions", "search_queries", "search_results",
            "sources", "source_snapshots", "citations", "cache_entries",
        }
        assert all(value == 0 for value in stats.values())


def test_default_ttl_ist_begrenzt():
    assert 60.0 <= DEFAULT_CACHE_TTL_S <= 86400.0
