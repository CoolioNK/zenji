"""Tests: ZENJI Core (Phase 2) – Orchestrierung, Fallback, Nachbereitung."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.database.database import Database
from app.database.migrations import run_migrations
from app.engines.communication_engine import CommunicationManager
from app.engines.context_engine import ContextEngine
from app.engines.llm_engine import LLMEngine
from app.engines.memory_engine import MemoryEngine
from app.engines.personality_engine import PersonalityEngine
from app.engines.policy_engine import PolicyEngine
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService
from app.services.conversation_service import ConversationService
from app.services.settings_service import SettingsService
from app.services.zenji_core import ZenjiCore
from tests.conftest import FAKE_REPLY, FakeProvider


class _Harness:
    """Vollständige Service-Umgebung mit Core (FakeProvider, keine SSD)."""

    def __init__(self, tmp_path) -> None:
        settings = Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]
        self.db = Database(settings)
        self.db.create_schema()
        run_migrations(self.db.engine)
        self.provider = FakeProvider()
        self.settings_service = SettingsService(settings)
        self.conversation_service = ConversationService()
        self.personality = PersonalityEngine()
        self.policy = PolicyEngine()
        self.memory = MemoryEngine()
        self.context = ContextEngine()
        self.communication = CommunicationManager()
        with self.db.session() as session:
            self.memory.init_search(session)
        self.core = ZenjiCore(
            settings_service=self.settings_service,
            conversation_service=self.conversation_service,
            personality_engine=self.personality,
            policy_engine=self.policy,
            memory_engine=self.memory,
            context_engine=self.context,
            communication_engine=self.communication,
        )
        self.chat_service = ChatService(
            database=self.db,
            engine=LLMEngine(self.provider),
            settings_service=self.settings_service,
            conversation_service=self.conversation_service,
            core=self.core,
        )


# --- Voller Chat-Durchlauf mit Core --------------------------------------------------


async def test_send_message_mit_core_erzeugt_orchestrierten_kontext(tmp_path):
    harness = _Harness(tmp_path)
    turn = await harness.chat_service.send_message(
        ChatRequest(message="Hallo ZENJI, wer bist du?")
    )
    assert turn.assistant_message.content == FAKE_REPLY
    assert len(harness.provider.chat_calls) == 1
    call = harness.provider.chat_calls[0]
    # Rollenfolge bleibt konform:
    assert call["roles"][0] == "system"
    assert call["roles"][1] == "user"
    system = call["messages"][0].content
    # Alle Kernabschnitte sind enthalten:
    assert "## Identität" in system
    assert "## Persönlichkeit" in system
    assert "Name: Zenji" in system
    assert "## Regeln" in system
    assert "Verbindliche Systemregeln" in system


async def test_merkwort_im_chat_erzeugt_erinnerung(tmp_path):
    harness = _Harness(tmp_path)
    await harness.chat_service.send_message(
        ChatRequest(message="Merke dir: Ich arbeite an Projekt Helios")
    )
    with harness.db.session() as session:
        memories = harness.memory.list(session, status="active")
        assert len(memories) == 1
        assert memories[0].source == "chat"
        assert memories[0].content == "Ich arbeite an Projekt Helios"
        assert memories[0].memory_type == "project"


async def test_verwendete_erinnerung_bekommt_last_used(tmp_path):
    harness = _Harness(tmp_path)
    # Erinnerung vorab anlegen:
    with harness.db.session() as session:
        memory, _ = harness.memory.create(
            session, content="Der Nutzer heißt Maximilian.", memory_type="preference"
        )
        memory_id = memory.id

    turn = await harness.chat_service.send_message(
        ChatRequest(message="Weißt du, wie Maximilian heißt?")
    )
    assert turn.assistant_message.content == FAKE_REPLY

    with harness.db.session() as session:
        refreshed = harness.memory.get(session, memory_id)
        assert refreshed.last_used_at is not None


async def test_erinnerung_landet_im_systemkontext(tmp_path):
    harness = _Harness(tmp_path)
    with harness.db.session() as session:
        harness.memory.create(
            session,
            content="Der Nutzer bevorzugt strukturierte Listen.",
            memory_type="preference",
            relevance=0.9,
        )
    await harness.chat_service.send_message(
        ChatRequest(message="Wie soll ich antworten,Listen oder Fließtext?")
    )
    call = harness.provider.chat_calls[-1]
    system = call["messages"][0].content
    assert "## Erinnerungen" in system
    assert "[INHALT_BEGINN]" in system
    assert "Der Nutzer bevorzugt strukturierte Listen." in system


# --- Core direkt ---------------------------------------------------------------------


async def test_prepare_turn_ohne_konversation(tmp_path):
    harness = _Harness(tmp_path)
    with harness.db.session() as session:
        prepared = await harness.core.prepare_turn(
            session, conversation_id=None, user_message="Testfrage"
        )
    assert prepared.messages[0].role == "system"
    assert prepared.personality_name == "Zenji"
    assert prepared.active_policy_count >= 7
    assert prepared.mode == "casual"
    assert prepared.plan.budget_tokens > 0


async def test_context_preview_ohne_konversation(tmp_path):
    harness = _Harness(tmp_path)
    with harness.db.session() as session:
        preview = await harness.core.context_preview(
            session, conversation_id=None, sample_message="Was kannst du?"
        )
    assert preview["messages"][0]["role"] == "system"
    assert preview["budget_tokens"] > 0
    keys = {section["key"] for section in preview["sections"]}
    assert {"identity", "personality", "communication", "policies"} <= keys
    assert preview["mode"] == "casual"


def test_status_liefert_kern_zustaende(tmp_path):
    harness = _Harness(tmp_path)
    with harness.db.session() as session:
        settings = harness.settings_service.effective(session)
        status = harness.core.status(session, settings=settings)
    assert status["personality"] == "Zenji"
    assert status["active_policies"] >= 7
    assert status["model"] == "qwen3:8b"
    assert status["memories"]["total"] == 0
    # v0.3.0: Kommunikationsmodi im Status:
    mode_keys = {mode["key"] for mode in status["communication_modes"]}
    assert mode_keys == {"casual", "roast", "focus", "empathy", "open_talk"}
    assert status["communication_default_mode"] == "casual"


async def test_finalisierung_toleriert_fehler(tmp_path):
    """finalize darf niemals den Chat-Abschluss sprengen (fail-soft)."""
    harness = _Harness(tmp_path)
    with harness.db.session() as session:
        # defekter Inhalt (löst ValidationError aus) darf nicht crashen:
        created = harness.core.finalize_turn(
            session,
            conversation_id="egal",
            user_text="Merke dir: Ich arbeite an Projekt Delphi",
            assistant_text="Antwort",
            used_memory_ids=["nicht-existierend"],
        )
        assert created  # Merkwort wurde trotzdem erkannt


# --- Phase-1-Fallback ohne Core bleibt identisch ----------------------------------------


async def test_chat_service_ohne_core_phase1_verhalten(tmp_path):
    settings = Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]
    db = Database(settings)
    db.create_schema()
    run_migrations(db.engine)
    provider = FakeProvider()
    service = ChatService(
        database=db,
        engine=LLMEngine(provider),
        settings_service=SettingsService(settings),
    )
    await service.send_message(ChatRequest(message="Hallo"))
    call = provider.chat_calls[0]
    # Phase 1: Persona-Systemprompt (ohne Erinnerungs-/Regelabschnitte):
    assert call["roles"] == ["system", "user"]
    assert "## Erinnerungen" not in call["messages"][0].content
    assert "## Regeln" not in call["messages"][0].content
