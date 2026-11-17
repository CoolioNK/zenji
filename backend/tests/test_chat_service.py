"""Tests: Conversation- und Chat-Service (mit FakeProvider)."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.exceptions import ConversationNotFoundError, ModelNotFoundError
from app.database.database import Database
from app.engines.llm_engine import LLMEngine
from app.schemas.chat import ChatRequest
from app.schemas.settings import SettingsPatch
from app.services.chat_service import ChatService
from app.services.conversation_service import ConversationService
from app.services.settings_service import SettingsService
from tests.conftest import FAKE_REPLY, FakeProvider


def _services(tmp_path, provider: FakeProvider | None = None):
    settings = Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]
    db = Database(settings)
    db.create_schema()
    provider = provider or FakeProvider()
    engine = LLMEngine(provider)
    settings_service = SettingsService(settings)
    conversation_service = ConversationService()
    chat_service = ChatService(
        database=db,
        engine=engine,
        settings_service=settings_service,
        conversation_service=conversation_service,
    )
    return db, conversation_service, chat_service, provider, settings_service


async def test_send_message_speichert_beide_nachrichten(tmp_path):
    db, conversations, chat, provider, _ = _services(tmp_path)
    request = ChatRequest(message="Was ist ZENJI?")
    turn = await chat.send_message(request)

    assert turn.user_message.role == "user"
    assert turn.user_message.content == "Was ist ZENJI?"
    assert turn.assistant_message.role == "assistant"
    assert turn.assistant_message.content == FAKE_REPLY

    with db.session() as session:
        detail = conversations.get_conversation(session, turn.conversation_id)
    assert len(detail.messages) == 2
    # Titel aus erster Anfrage abgeleitet
    assert detail.title == "Was ist ZENJI?"


async def test_persona_wird_als_systemprompt_gesendet(tmp_path):
    db, conversations, chat, provider, _ = _services(tmp_path)
    await chat.send_message(ChatRequest(message="Hallo"))
    call = provider.chat_calls[0]
    assert call["roles"][0] == "system"
    assert "Zenji Ango" in call["messages"][0].content
    assert call["roles"][1] == "user"


async def test_verlauf_wird_in_kontext_einbezogen(tmp_path):
    db, conversations, chat, provider, _ = _services(tmp_path)
    turn1 = await chat.send_message(ChatRequest(message="Erste Frage"))
    await chat.send_message(
        ChatRequest(conversation_id=turn1.conversation_id, message="Zweite Frage")
    )
    second_call = provider.chat_calls[1]
    roles = second_call["roles"]
    assert roles == ["system", "user", "assistant", "user"]
    assert second_call["messages"][2].content == FAKE_REPLY


async def test_stream_erzeugt_eventsequenz_und_speichert(tmp_path):
    db, conversations, chat, provider, _ = _services(tmp_path)
    request = ChatRequest(message="Erzähl mir was")
    events = []
    async for event_bytes in chat.stream_message(request):
        events.append(event_bytes.decode("utf-8"))

    joined = "".join(events)
    assert joined.startswith("event: start\n")
    assert "event: delta\n" in joined
    assert joined.rstrip().endswith("event: done\n") or "event: done" in joined

    # Konversation wurde automatisch angelegt und beide Nachrichten gespeichert
    with db.session() as session:
        listed = conversations.list_conversations(session)
        assert len(listed) == 1
        assert listed[0].message_count == 2


async def test_stream_in_bestehende_konversation(tmp_path):
    db, conversations, chat, provider, _ = _services(tmp_path)
    with db.session() as session:
        conv = conversations.create(session, "Thema X")
        conv_id = conv.id

    events = [e.decode("utf-8") async for e in chat.stream_message(
        ChatRequest(conversation_id=conv_id, message="Weiter")
    )]
    assert any('"conversation_id": "%s"' % conv_id in e for e in events)
    with db.session() as session:
        detail = conversations.get_conversation(session, conv_id)
        assert detail.title == "Thema X"
        assert detail.message_count == 2


async def test_preflight_wirft_bei_fehlender_konversation(tmp_path):
    db, conversations, chat, provider, _ = _services(tmp_path)
    import uuid

    unbekannt = uuid.uuid4().hex
    with pytest.raises(ConversationNotFoundError):
        await chat.preflight(ChatRequest(conversation_id=unbekannt, message="hi"))


async def test_preflight_wirft_bei_fehlendem_modell(tmp_path):
    db, conversations, chat, provider, _ = _services(tmp_path, FakeProvider(models=("llama3.1:8b",)))
    with pytest.raises(ModelNotFoundError):
        await chat.preflight(ChatRequest(message="hi"))


async def test_settings_aendern_wirkt_auf_chat(tmp_path):
    db, conversations, chat, provider, settings_service = _services(
        tmp_path, FakeProvider(models=("qwen3:8b", "llama3.1:8b"))
    )
    with db.session() as session:
        settings_service.patch(
            session, SettingsPatch(llm={"temperature": 0.2})
        )
    await chat.send_message(ChatRequest(message="Frage"))
    call = provider.chat_calls[0]
    assert call["options"].temperature == 0.2
