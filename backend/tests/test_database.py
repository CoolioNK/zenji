"""Tests: Datenbank (SQLite, Schema, Kaskaden, Fehlerübersetzung)."""

from __future__ import annotations

import sqlalchemy as sa
import pytest

from app.core.config import Settings
from app.core.exceptions import StorageUnavailableError
from app.database.database import Database
from app.database.models import Base, ConversationModel, MessageModel


def _db(tmp_path) -> Database:
    settings = Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]
    return Database(settings)


def test_schema_erstellung_und_tabellen(tmp_path):
    db = _db(tmp_path)
    db.create_schema()
    assert db.db_path.exists()
    assert db.is_ready()
    with db.engine.connect() as conn:
        tables = {row[0] for row in conn.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table'"))}
    assert {"conversations", "messages", "settings"} <= tables
    db.dispose()


def test_datum_liegt_unter_ssd_datenverzeichnis(tmp_path):
    db = _db(tmp_path)
    db.create_schema()
    assert db.db_path.parent == tmp_path / "ZENJI" / "data"
    db.dispose()


def test_kaskadieren_löscht_nachrichten_mit(tmp_path):
    db = _db(tmp_path)
    db.create_schema()
    with db.session() as session:
        conv = ConversationModel(title="Test")
        session.add(conv)
        session.flush()
        for i in range(3):
            session.add(MessageModel(conversation_id=conv.id, role="user", content=f"m{i}"))
    with db.session() as session:
        conv = session.get(ConversationModel, conv.id)
        session.delete(conv)
    with db.engine.connect() as conn:
        count = conn.execute(sa.text("SELECT COUNT(*) FROM messages")).scalar_one()
        conv_count = conn.execute(sa.text("SELECT COUNT(*) FROM conversations")).scalar_one()
    assert count == 0
    assert conv_count == 0
    db.dispose()


def test_fremdschluessel_aktiv(tmp_path):
    db = _db(tmp_path)
    db.create_schema()
    with pytest.raises(sa.exc.IntegrityError):
        with db.session() as session:
            session.add(MessageModel(conversation_id="nichtexistent", role="user", content="x"))
    db.dispose()


def test_ungueltige_rolle_wird_abgelehnt(tmp_path):
    db = _db(tmp_path)
    db.create_schema()
    with db.session() as session:
        conv = ConversationModel(title="t")
        session.add(conv)
        session.flush()
    with pytest.raises(sa.exc.IntegrityError):
        with db.session() as session:
            session.add(MessageModel(conversation_id=conv.id, role="moderator", content="x"))
    db.dispose()


def test_fehlende_ssd_fuehrt_zu_klarer_meldung(tmp_path):
    settings = Settings(_env_file=None, ssd_root=tmp_path / "fehlt")  # type: ignore[arg-type]
    db = Database(settings)
    with pytest.raises(StorageUnavailableError) as excinfo:
        db.create_schema()
    assert "SSD" in str(excinfo.value) or "beschreibbar" in str(excinfo.value)


def test_rollback_bei_fehler_innerhalb_session(tmp_path):
    db = _db(tmp_path)
    db.create_schema()
    with pytest.raises(RuntimeError):
        with db.session() as session:
            session.add(ConversationModel(title="bleibt raus"))
            raise RuntimeError("absichtlicher Fehler")
    with db.engine.connect() as conn:
        count = conn.execute(sa.text("SELECT COUNT(*) FROM conversations")).scalar_one()
    assert count == 0
    db.dispose()
