"""Tests: Datenbank-Migrationen und Seeding (Phase 2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.core.config import Settings
from app.database.database import Database
from app.database.migrations import LATEST_VERSION, current_version, run_migrations
from app.database.models import (
    MemoryModel,
    PersonalityModel,
    PolicyModel,
    SchemaVersionModel,
)


def _db(tmp_path: Path) -> Database:
    settings = Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]
    return Database(settings)


def test_fresh_database_erhaelt_tabellen_und_seeds(tmp_path):
    db = _db(tmp_path)
    db.create_schema()
    version = run_migrations(db.engine)

    assert version == LATEST_VERSION
    assert current_version(db.engine) == LATEST_VERSION

    with db.session() as session:
        profiles = list(session.scalars(select(PersonalityModel)))
        assert len(profiles) == 4
        names = {p.name for p in profiles}
        assert names == {"Neutral", "Professional", "Friendly", "Casual"}

        active = [p for p in profiles if p.is_active]
        assert len(active) == 1
        assert active[0].name == "Neutral"
        assert active[0].is_system is True

        rules = list(session.scalars(select(PolicyModel)))
        assert len(rules) == 6
        system_rules = [r for r in rules if r.source == "system"]
        assert len(system_rules) == 5
        assert {r.id for r in system_rules} >= {"zenji_identity", "injection_defense"}
        # Zenji-Identität hat höchste Priorität:
        identity = next(r for r in rules if r.id == "zenji_identity")
        assert identity.priority == 100

        # Metadaten-Tabelle konsistent:
        meta = session.get(SchemaVersionModel, 1)
        assert meta is not None
        assert meta.version == LATEST_VERSION


def test_migration_ist_idempotent(tmp_path):
    db = _db(tmp_path)
    db.create_schema()
    run_migrations(db.engine)
    # Erneut ausführen darf nichts verändern:
    assert run_migrations(db.engine) == LATEST_VERSION
    with db.session() as session:
        assert len(list(session.scalars(select(PersonalityModel)))) == 4
        assert len(list(session.scalars(select(PolicyModel)))) == 6


def test_migration_erhaelt_bestehende_konversationen(tmp_path):
    """Phase-1-Datenbank (nur conversations/messages/settings) → Migration darf
    keine bestehenden Konversationen verlieren."""
    db = _db(tmp_path)
    db.create_schema()

    # Bestehende Konversation anlegen:
    from app.database.models import ConversationModel, MessageModel

    with db.session() as session:
        conversation = ConversationModel(title="Phase 1 Chat")
        session.add(conversation)
        session.flush()
        session.add(
            MessageModel(
                conversation_id=conversation.id,
                role="user",
                content="Wichtige Phase-1-Nachricht",
            )
        )
        session.add(
            MessageModel(
                conversation_id=conversation.id,
                role="assistant",
                content="Phase-1-Antwort",
            )
        )
        conversation_id = conversation.id

    # Simuliere Phase-1-Zustand: neue Tabellen entfernen, Versions-Stufe 0:
    with db.engine.connect() as conn:
        for table in ("memories", "personalities", "policies", "schema_version"):
            conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
        conn.execute(text("PRAGMA user_version = 0"))
        conn.commit()
    assert current_version(db.engine) == 0

    # Migration erneut ausführen:
    db.create_schema()  # legt die Tabellen neu an (idempotent)
    run_migrations(db.engine)

    with db.session() as session:
        # Phase-1-Konversation vollständig erhalten:
        conversation = session.get(ConversationModel, conversation_id)
        assert conversation is not None
        assert conversation.title == "Phase 1 Chat"
        messages = list(
            session.scalars(
                select(MessageModel).where(
                    MessageModel.conversation_id == conversation_id
                )
            )
        )
        assert len(messages) == 2
        assert messages[0].content == "Wichtige Phase-1-Nachricht"

        # Seeds trotzdem korrekt angelegt:
        assert len(list(session.scalars(select(PersonalityModel)))) == 4
        assert current_version(db.engine) == LATEST_VERSION


def test_seed_niemand_aktiv_ueberschreibt_nutzeraktivierung(tmp_path):
    """Wenn bereits ein Nutzerprofil aktiv ist, darf das Seed das nicht ändern."""
    db = _db(tmp_path)
    db.create_schema()
    run_migrations(db.engine)

    with db.session() as session:
        # Nutzerprofil aktivieren (Systemprofile bleiben aktiv, sind aber nicht mehr aktiv):
        custom = PersonalityModel(name="Mein Profil", is_system=False, is_active=True)
        session.add(custom)
        session.flush()
        session.execute(
            text("UPDATE personalities SET is_active = 0 WHERE is_system = 1")
        )
        session.flush()

    # Seeding erneut (z. B. nach Restore) darf nichts an der Aktivierung ändern:
    db.create_schema()
    run_migrations(db.engine)
    with db.session() as session:
        active = list(
            session.scalars(
                select(PersonalityModel).where(PersonalityModel.is_active.is_(True))
            )
        )
        assert len(active) == 1
        assert active[0].name == "Mein Profil"


def test_memories_tabelle_habt_hash_index(tmp_path):
    """content_hash ist indiziert (Duplikaterkennung performant)."""
    db = _db(tmp_path)
    db.create_schema()
    run_migrations(db.engine)
    with db.engine.connect() as conn:
        rows = conn.execute(
            text("PRAGMA index_list('memories')")
        ).fetchall()
    assert any("content_hash" in (r[1] or "") for r in rows)
