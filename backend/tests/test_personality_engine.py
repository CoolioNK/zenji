"""Tests: Personality Engine (Phase 2)."""

from __future__ import annotations

import json

import pytest

from app.core.config import Settings
from app.core.exceptions import (
    PersonalityNameTakenError,
    PersonalityNotFoundError,
    PersonalityProtectedError,
    ValidationError,
)
from app.database.database import Database
from app.database.migrations import run_migrations
from app.engines.personality_engine import PersonalityEngine


@pytest.fixture()
def db(tmp_path):
    settings = Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]
    database = Database(settings)
    database.create_schema()
    run_migrations(database.engine)
    return database


@pytest.fixture()
def engine(db):
    return PersonalityEngine()


def test_seed_profile_geladen_und_neutral_aktiv(db, engine):
    with db.session() as session:
        profiles = engine.list(session)
        assert len(profiles) == 4
        active = engine.require_active(session)
        assert active is not None
        assert active.name == "Neutral"
        assert active.is_system is True


def test_kompilierung_enthaelt_alle_abschnitte(db, engine):
    with db.session() as session:
        active = engine.require_active(session)
        text = engine.compile_context(active)
    assert text.startswith("## Persönlichkeit")
    assert "Name: Neutral" in text
    assert "Identität:" in text
    assert "Formalität:" in text
    assert "Humor:" in text
    assert "Direktheit:" in text
    assert "Kreativität:" in text
    assert "Antworte ausführlich genug" in text  # balanced
    assert "Verhalten in besonderen Situationen:" in text
    assert "Situation 'Fehler oder Unsicherheit':" in text


def test_kompilierung_spiegelt_profil_eigenschaften(db, engine):
    with db.session() as session:
        professional = engine.get(session, engine.list(session)[1].id)
        text = engine.compile_context(professional)
    assert "Name: Professional" in text
    assert "sehr formell" in text
    assert "Antworte ausführlich und strukturiert" in text  # detailed

    casual = engine.get(session, engine.list(session)[3].id)
    casual_text = engine.compile_context(casual)
    assert "Name: Casual" in casual_text
    assert "Antworte knapp" in casual_text  # short


def test_ohne_profil_fallback_block(db, engine):
    text = engine.compile_context(None)
    assert "Kein Profil aktiv" in text
    assert "## Persönlichkeit" in text


def test_eigenes_profil_erstellen_und_aktivieren(db, engine):
    with db.session() as session:
        profile = engine.create(
            session,
            {
                "name": "Zenji Tester",
                "identity": "Test-Identität",
                "base_personality": "custom",
                "formality": 0.9,
                "is_active": True,
            },
        )
        active = engine.require_active(session)
        assert active is not None
        assert active.id == profile.id
        assert active.name == "Zenji Tester"
        # Genau ein Profil aktiv:
        assert sum(1 for p in engine.list(session) if p.is_active) == 1


def test_profilname_doppelt_abgelehnt(db, engine):
    with db.session() as session:
        engine.create(session, {"name": "Duplikat"})
        with pytest.raises(PersonalityNameTakenError):
            engine.create(session, {"name": "Duplikat"})


def test_profil_update(db, engine):
    with db.session() as session:
        profile = engine.create(session, {"name": "Wandelbar"})
        updated = engine.update(
            session, profile.id, {"humor": 0.8, "identity": "Neu"}
        )
        assert updated.humor == 0.8
        assert updated.identity == "Neu"
        # Ungültiger Name:
        with pytest.raises(ValidationError):
            engine.update(session, profile.id, {"name": " "})


def test_systemprofil_geschuetzt(db, engine):
    with db.session() as session:
        neutral = engine.get(session, engine.list(session)[0].id)
        assert neutral.is_system
        with pytest.raises(PersonalityProtectedError):
            engine.delete(session, neutral.id)


def test_aktives_profil_geschuetzt(db, engine):
    with db.session() as session:
        profile = engine.create(session, {"name": "Aktiv"} )
        engine.activate(session, profile.id)
        with pytest.raises(PersonalityProtectedError):
            engine.delete(session, profile.id)


def test_inaktives_nutzerprofil_loeschbar(db, engine):
    with db.session() as session:
        profile = engine.create(session, {"name": "Weg damit"})
        engine.delete(session, profile.id)
        with pytest.raises(PersonalityNotFoundError):
            engine.get(session, profile.id)


def test_unbekanntes_profil_404(db, engine):
    with db.session() as session:
        with pytest.raises(PersonalityNotFoundError):
            engine.get(session, "gibt-es-nicht")


def test_update_aktiviert_profil(db, engine):
    with db.session() as session:
        profile = engine.create(session, {"name": "Aktivierbar"})
        engine.update(session, profile.id, {"is_active": True})
        active = engine.require_active(session)
        assert active is not None
        assert active.id == profile.id


def test_situationsverhalten_als_json_gespeichert(db, engine):
    behavior = {"Krisensituation": "Bleib ruhig und strukturiert."}
    with db.session() as session:
        profile = engine.create(
            session,
            {
                "name": "Situationstest",
                "situational_behavior": json.dumps(behavior, ensure_ascii=False),
            },
        )
        assert profile.behavior_map() == behavior
