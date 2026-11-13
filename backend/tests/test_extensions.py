"""Tests: Erweiterungspunkte (ExtensionRegistry, Interfaces für Phase 2)."""

from __future__ import annotations

from typing import Any

import pytest

from app.core.extensions import ExtensionRegistry
from app.interfaces.base import (
    ImageEngine,
    MemoryEngine,
    PluginManager,
    PolicyEngine,
    RAGEngine,
    ToolEngine,
    ToolSpec,
    WebEngine,
    ZenjiEngine,
)


class _DummyEngine(ZenjiEngine):
    name = "dummy"

    async def start(self) -> None:
        self.started = True  # type: ignore[attr-defined]

    async def stop(self) -> None:
        self.stopped = True  # type: ignore[attr-defined]


async def test_registry_register_get_stop():
    registry = ExtensionRegistry()
    engine = _DummyEngine()
    registry.register(engine)
    assert registry.has("dummy")
    assert registry.get("dummy") is engine
    assert registry.names() == ["dummy"]
    assert registry.get("fehlt") is None  # fail-soft

    await registry.start_all()
    assert engine.started is True
    await registry.stop_all()
    assert engine.stopped is True
    assert registry.names() == []


def test_alle_engine_schnittstellen_sind_abstrakt():
    for cls in (PolicyEngine, MemoryEngine, WebEngine, ToolEngine, PluginManager, RAGEngine, ImageEngine):
        with pytest.raises(TypeError):
            cls()  # type: ignore[abstract]


def test_toolspec_kann_deklariert_werden():
    spec = ToolSpec(name="web_search", description="Websuche", parameters={"query": "str"})
    assert spec.name == "web_search"


async def test_chat_pfad_laeuft_ohne_engines(tmp_path):
    """Phase 1: keine Engine registriert → Chat läuft unverändert."""
    from app.core.config import Settings
    from app.database.database import Database
    from app.engines.llm_engine import LLMEngine
    from app.schemas.chat import ChatRequest
    from app.services.chat_service import ChatService
    from app.services.conversation_service import ConversationService
    from app.services.settings_service import SettingsService
    from tests.conftest import FakeProvider

    settings = Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]
    db = Database(settings)
    db.create_schema()
    chat = ChatService(
        database=db,
        engine=LLMEngine(FakeProvider()),
        settings_service=SettingsService(settings),
        conversation_service=ConversationService(),
        extensions=ExtensionRegistry(),  # leer
    )
    turn = await chat.send_message(ChatRequest(message="Test ohne Engines"))
    assert turn.assistant_message.content
    db.dispose()
