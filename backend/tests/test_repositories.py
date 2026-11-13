"""Tests: Repositories (Konversationen, Nachrichten, Einstellungen)."""

from __future__ import annotations

import json

import pytest

from app.core.config import Settings
from app.database.database import Database
from app.database.repositories.conversations import ConversationRepository
from app.database.repositories.messages import MessageRepository
from app.database.repositories.settings import SettingsRepository


def _db(tmp_path) -> Database:
    settings = Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]
    db = Database(settings)
    db.create_schema()
    return db


def test_konversation_crud(tmp_path):
    db = _db(tmp_path)
    repo = ConversationRepository()
    with db.session() as session:
        conv = repo.create(session, "Erster Chat")
        second = repo.create(session, "Zweiter Chat")
        assert conv.title == "Erster Chat"
        assert second.id != conv.id

    with db.session() as session:
        listed = repo.list_all(session)
        assert len(listed) == 2

        renamed = repo.rename(session, conv.id, "Umbenannt")
        assert renamed.title == "Umbenannt"

        assert repo.rename(session, "unbekannt", "x") is None
        assert repo.delete(session, "unbekannt") is False
        assert repo.delete(session, second.id) is True
    db.dispose()


def test_nachrichten_historie_und_reihenfolge(tmp_path):
    db = _db(tmp_path)
    conv_repo = ConversationRepository()
    msg_repo = MessageRepository()
    with db.session() as session:
        conv = conv_repo.create(session, "Historie")
        for i in range(5):
            msg_repo.add(session, conv.id, "user" if i % 2 == 0 else "assistant", f"Nachricht {i}")

    with db.session() as session:
        history = msg_repo.history(session, conv.id, limit=3)
        assert [m.content for m in history] == ["Nachricht 2", "Nachricht 3", "Nachricht 4"]
        full = msg_repo.by_conversation(session, conv.id)
        assert [m.content for m in full] == [f"Nachricht {i}" for i in range(5)]

    with pytest.raises(ValueError):  # noqa: PT012 – unbekannte Rolle
        with db.session() as session:
            msg_repo.add(session, conv.id, "admin", "illegal")
    db.dispose()


def test_nachrichtenzaehler_ohne_n_plus_1(tmp_path):
    db = _db(tmp_path)
    conv_repo = ConversationRepository()
    msg_repo = MessageRepository()
    with db.session() as session:
        a = conv_repo.create(session, "A")
        b = conv_repo.create(session, "B")
        for i in range(2):
            msg_repo.add(session, a.id, "user", f"a{i}")
        msg_repo.add(session, b.id, "user", "b0")
    with db.session() as session:
        counts = conv_repo.count_messages(session, [a.id, b.id])
    assert counts == {a.id: 2, b.id: 1}
    db.dispose()


def test_settings_repository_set_and_get(tmp_path):
    db = _db(tmp_path)
    repo = SettingsRepository()
    with db.session() as session:
        assert repo.get(session, "llm") is None
        repo.set(session, "llm", json.dumps({"model": "qwen3:8b"}))
        repo.set(session, "llm", json.dumps({"model": "llama3:8b"}))  # Update
        assert json.loads(repo.get(session, "llm")) == {"model": "llama3:8b"}
    db.dispose()
