"""Tests: Memory Engine (Phase 2) – CRUD, Suche, Duplikate, Veralten, Auswahl."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.exceptions import MemoryNotFoundError, ValidationError
from app.database.database import Database
from app.database.migrations import run_migrations
from app.database.repositories.memories import MemoryRepository
from app.engines.memory_engine import MemoryEngine


@pytest.fixture()
def db(tmp_path):
    settings = Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]
    database = Database(settings)
    database.create_schema()
    run_migrations(database.engine)
    return database


@pytest.fixture()
def engine(db):
    engine = MemoryEngine()
    with db.session() as session:
        engine.init_search(session)
    return engine


# --- CRUD & Duplikate ------------------------------------------------------------


def test_erinnerung_anlegen_mit_allen_feldern(db, engine):
    with db.session() as session:
        memory, merged = engine.create(
            session,
            content="Der Nutzer heißt Max Mustermann.",
            category="identität",
            memory_type="preference",
            relevance=0.8,
        )
        assert merged is False
        assert memory.id
        assert memory.content_hash
        assert memory.status == "active"
        assert memory.source == "user"
        assert memory.created_at is not None


def test_duplikat_wird_zusammengefuehrt_nicht_doppelt(db, engine):
    with db.session() as session:
        first, merged1 = engine.create(
            session, content="Der Nutzer heißt Max Mustermann.", relevance=0.5
        )
        second, merged2 = engine.create(
            session, content="  der Nutzer heißt Max Mustermann.  ", relevance=0.6
        )
        assert merged1 is False
        assert merged2 is True
        assert second.id == first.id  # bestehende Erinnerung wurde aktualisiert
        assert len(engine.list(session, status="active")) == 1
        # Relevanz gestiegen:
        assert second.relevance > 0.5


def test_leerer_inhalt_abgelehnt(db, engine):
    with db.session() as session:
        with pytest.raises(ValidationError):
            engine.create(session, content="   ")


def test_unbekannter_typ_abgelehnt(db, engine):
    with db.session() as session:
        with pytest.raises(ValidationError):
            engine.create(session, content="Test", memory_type="hypothese")


def test_update_und_loeschen(db, engine):
    with db.session() as session:
        memory, _ = engine.create(session, content="Alte Notiz")
        updated = engine.update(session, memory.id, {"content": "Neue Notiz"})
        assert updated.content == "Neue Notiz"
        engine.delete(session, memory.id)
        with pytest.raises(MemoryNotFoundError):
            engine.get(session, memory.id)
        # Löschprüfung: FTS-Index ebenfalls geräumt:
        results = MemoryRepository()
        # (kein direkter Index-Zugriff nötig – Suche liefert nichts mehr)
        results2 = engine.search(session, "Notiz")
        assert results2 == []


def test_404_bei_unbekannter_id(db, engine):
    with db.session() as session:
        with pytest.raises(MemoryNotFoundError):
            engine.get(session, "existiert-nicht")


# --- Veralten & Widersprüche -------------------------------------------------------


def test_neuere_aehnliche_erinnerung_verdraengt_aeltere(db, engine):
    with db.session() as session:
        old, _ = engine.create(
            session, content="Der Nutzer heißt Max", memory_type="preference"
        )
        new, _ = engine.create(
            session, content="Der Nutzer heißt Maxi", memory_type="preference"
        )
        session.refresh(old)
        assert old.status == "superseded"
        assert new.status == "active"
        assert new.supersedes_id == old.id
        # Nur die neue ist aktiv:
        active_contents = [
            m.content for m in engine.list(session, status="active")
        ]
        assert active_contents == ["Der Nutzer heißt Maxi"]


def test_supersede_gilt_nur_innerhalb_des_typs(db, engine):
    with db.session() as session:
        project, _ = engine.create(
            session, content="Der Nutzer heißt Max", memory_type="project"
        )
        preference, _ = engine.create(
            session, content="Der Nutzer heißt Maxi", memory_type="preference"
        )
        session.refresh(project)
        # Unterschiedlicher Typ: keine Verdrängung, stattdessen Konfliktregel.
        assert project.status == "active"
        assert preference.status == "active"


def test_widerspruch_wird_markiert_und_beide_bleiben_aktiv(db, engine):
    with db.session() as session:
        # Ähnlichkeit liegt zwischen 0,5 und 0,85 → kein Supersede, beide aktiv.
        first, _ = engine.create(
            session,
            content="Der Nutzer arbeitet an Projekt Phoenix",
            memory_type="long_term",
            relevance=0.9,
        )
        second, _ = engine.create(
            session,
            content="Der Nutzer arbeitet an Projekt Berlin mit dem neuen Team",
            memory_type="long_term",
            relevance=0.9,
        )
        assert first.status == "active"
        assert second.status == "active"
        relevant = engine.collect_relevant(
            session, "Was mache ich im Projekt?", limit=5
        )
        conflicts = [item for item in relevant if item.conflict]
        assert len(conflicts) >= 1
        # Beide Erinnerungen können im Kontext landen (Konfliktregel fragt nach):
        ids = {item.memory.id for item in relevant}
        assert {first.id, second.id} & ids


# --- Automatische Auswahl ------------------------------------------------------------


def test_collect_relevant_ranking_nach_score(db, engine):
    with db.session() as session:
        engine.create(
            session,
            content="Der Nutzer bevorzugt kurze Antworten.",
            memory_type="preference",
            relevance=0.9,
        )
        engine.create(
            session,
            content="Das Lieblingsprojekt des Nutzers heißt Zenji.",
            memory_type="project",
            relevance=0.9,
        )
        relevant = engine.collect_relevant(
            session, "Welche Antworten bevorzugt der Nutzer?"
        )
        assert relevant
        assert relevant[0].memory.memory_type == "preference"
        assert all(item.score > 0 for item in relevant)


def test_collect_relevant_fallback_ohne_treffer(db, engine):
    with db.session() as session:
        engine.create(
            session,
            content="Der Nutzer mag strukturierte Listen.",
            memory_type="preference",
            relevance=0.8,
        )
        relevant = engine.collect_relevant(session, "Wie ist das Wetter?")
        # Fallback: relevante aktive Erinnerungen werden trotzdem vorgeschlagen.
        assert relevant
        assert relevant[0].memory.memory_type in ("preference", "long_term")


def test_collect_relevant_ohne_gedaechtnis_leer(db, engine):
    with db.session() as session:
        relevant = engine.collect_relevant(session, "Was gibt es Neues?")
        assert relevant == []


# --- Merkmuster (Schritt 12) ------------------------------------------------------


def test_merkworte_werden_erkannt(db, engine):
    with db.session() as session:
        created = engine.remember_candidates(
            session,
            "Merke dir: Ich arbeite an Projekt Apollo",
            conversation_id="conv-123",
        )
        assert len(created) == 1
        memory = created[0]
        assert memory.content == "Ich arbeite an Projekt Apollo"
        assert memory.source == "chat"
        assert memory.source_ref == "conv-123"
        assert memory.memory_type == "project"
        assert memory.category == "projekt"


def test_namensnennung_als_praeferenz(db, engine):
    with db.session() as session:
        created = engine.remember_candidates(
            session, "Denk daran: Ich heiße Maria"
        )
        assert len(created) == 1
        assert created[0].memory_type == "preference"
        assert created[0].category == "identität"


def test_normale_nachricht_wird_nicht_gespeichert(db, engine):
    with db.session() as session:
        created = engine.remember_candidates(
            session, "Hallo ZENJI, wie geht es dir heute?"
        )
        assert created == []
        assert len(engine.list(session, status="active")) == 0


# --- Suche ------------------------------------------------------------------------


def test_suche_findet_inhalt(db, engine):
    with db.session() as session:
        engine.create(session, content="Der Nutzer arbeitet mit Python und FastAPI.")
        engine.create(session, content="Der Nutzer mag italienische Musik.")
        results = engine.search(session, "Python FastAPI")
        assert results
        assert "Python" in results[0][0].content


def test_suche_filter_typ_und_kategorie(db, engine):
    with db.session() as session:
        engine.create(
            session,
            content="Projekt Zenji nutzt SQLite.",
            memory_type="project",
            category="projekt",
        )
        engine.create(
            session,
            content="Projekt Zenji nutzt SQLite nicht.",
            memory_type="long_term",
            category="fakt",
        )
        results = engine.search(
            session, "SQLite", memory_type="project", category="projekt"
        )
        assert len(results) == 1
        assert results[0][0].memory_type == "project"


def test_suche_ignoriert_archivierte(db, engine):
    with db.session() as session:
        memory, _ = engine.create(session, content="Suchbarer Inhalt")
        engine.update(session, memory.id, {"status": "archived"})
        assert engine.search(session, "Suchbarer Inhalt") == []


def test_last_used_wird_gesetzt(db, engine):
    with db.session() as session:
        memory, _ = engine.create(session, content="Der Nutzer heißt Max.")
        assert memory.last_used_at is None
        engine.mark_used(session, [memory.id])
        session.refresh(memory)
        assert memory.last_used_at is not None


def test_stats_zaehlen_korrekt(db, engine):
    with db.session() as session:
        engine.create(session, content="A")
        engine.create(session, content="B")
        stats = engine.stats(session)
        assert stats["total"] == 2
        assert stats["active"] == 2
        assert stats["search_provider"] in ("fts5", "like")
