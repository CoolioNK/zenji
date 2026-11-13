"""Tests: LLM Engine und Modellverwaltung (mit FakeProvider)."""

from __future__ import annotations

import pytest

from app.core.exceptions import ModelNotFoundError, ProviderConnectionError
from app.engines.llm_engine import LLMEngine
from app.engines.model_manager import ModelManager, ModelStatus
from app.engines.providers.base import ChatMessage, LLMOptions
from tests.conftest import FAKE_REPLY, FakeProvider


def _engine(provider: FakeProvider) -> LLMEngine:
    return LLMEngine(provider)


async def test_generate_liefert_komplette_antwort():
    provider = FakeProvider(reply="Eine ruhige Antwort.")
    engine = _engine(provider)
    content, meta = await engine.generate(
        [ChatMessage(role="user", content="Hallo")],
        LLMOptions(),
        model="qwen3:8b",
        keep_alive="10m",
    )
    assert content == "Eine ruhige Antwort."
    assert meta["eval_count"] == 3
    assert provider.chat_calls[0]["model"] == "qwen3:8b"
    assert provider.chat_calls[0]["keep_alive"] == "10m"
    assert provider.chat_calls[0]["roles"] == ["user"]


async def test_stream_liefert_chunks():
    provider = FakeProvider(reply="Wort1 Wort2 Wort3")
    engine = _engine(provider)
    pieces = []
    async for chunk in engine.stream(
        [ChatMessage(role="user", content="hi")], LLMOptions(), model="qwen3:8b"
    ):
        pieces.append(chunk.content)
        if chunk.done:
            break
    assert "".join(pieces) == "Wort1 Wort2 Wort3"
    assert len(provider.stream_calls) == 1


async def test_options_werden_weitergereicht():
    provider = FakeProvider()
    engine = _engine(provider)
    options = LLMOptions(temperature=0.2, top_k=7, num_ctx=4096)
    await engine.generate([ChatMessage(role="user", content="x")], options, model="qwen3:8b")
    passed = provider.chat_calls[0]["options"]
    assert passed.temperature == 0.2
    assert passed.top_k == 7
    assert passed.num_ctx == 4096


async def test_ensure_model_available_wirft_bei_fehlendem_modell():
    provider = FakeProvider(models=("qwen3:8b",))
    engine = _engine(provider)
    await engine.ensure_model_available("qwen3:8b")  # ok
    with pytest.raises(ModelNotFoundError) as excinfo:
        await engine.ensure_model_available("llava:13b")
    assert "ollama pull" in excinfo.value.detail


async def test_ensure_model_available_wirft_bei_offline_provider():
    provider = FakeProvider(available=False)
    engine = _engine(provider)
    with pytest.raises(ProviderConnectionError):
        await engine.ensure_model_available("qwen3:8b")


async def test_provider_status_und_liste():
    engine = _engine(FakeProvider())
    status = await engine.provider_status()
    assert status.available
    models = await engine.list_models()
    assert models[0].name == "qwen3:8b"


async def test_model_manager_status_verstaendlich():
    provider = FakeProvider()
    manager = ModelManager(provider)
    status: ModelStatus = await manager.status_for("qwen3:8b")
    assert status.provider_available and status.model_available

    provider2 = FakeProvider(models=("qwen3:8b",))
    manager2 = ModelManager(provider2)
    status2 = await manager2.status_for("mistral:7b")
    assert status2.model_available is False
    assert "nicht geladen" in status2.message
    assert "ollama pull" in status2.message

    provider3 = FakeProvider(available=False)
    status3 = await ModelManager(provider3).status_for("qwen3:8b")
    assert status3.provider_available is False
