"""Tests: Ollama-Provider mit httpx.MockTransport (kein echter Ollama-Server)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import OllamaDefaults
from app.core.exceptions import (
    ConfigurationError,
    LLMResponseError,
    LLMTimeoutError,
    ModelNotFoundError,
    ProviderConnectionError,
)
from app.engines.providers import available_providers, create_provider, register_provider
from app.engines.providers.base import (
    ChatMessage,
    LLMOptions,
    LLMProvider,
    ProviderStatus,
    StreamChunk,
    strip_think_blocks,
)
from app.engines.providers.ollama import OllamaProvider

# Denk-Tags von Qwen3-artigen Modellen (als Konstante, um Quoting zu vermeiden).
THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"


def make_provider(handler) -> OllamaProvider:
    provider = OllamaProvider("http://mock:11434", OllamaDefaults(timeout=5, connect_timeout=2))
    provider._client = httpx.AsyncClient(
        base_url=provider._base_url, transport=httpx.MockTransport(handler)
    )
    return provider


def ndjson(*lines: dict) -> bytes:
    return ("\n".join(json.dumps(line) for line in lines) + "\n").encode()


def tags_payload() -> dict:
    return {
        "models": [
            {
                "name": "qwen3:8b",
                "size": 5_100_000_000,
                "modified_at": "2026-01-02T10:00:00Z",
                "details": {
                    "family": "qwen3",
                    "parameter_size": "8.2B",
                    "quantization_level": "Q4_K_M",
                },
            },
            {"name": "llama3.1:8b", "size": 4_900_000_000, "details": {"family": "llama"}},
        ]
    }


def stream_lines_plain() -> list[dict]:
    return [
        {"model": "qwen3:8b", "message": {"role": "assistant", "content": "Hallo "}, "done": False},
        {"model": "qwen3:8b", "message": {"role": "assistant", "content": "Welt"}, "done": False},
        {"model": "qwen3:8b", "message": {"role": "assistant", "content": ""}, "done": True, "eval_count": 7},
    ]


def handler_ok(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/api/version":
        return httpx.Response(200, json={"version": "0.40.16"})
    if path == "/api/tags":
        return httpx.Response(200, json=tags_payload())
    if path == "/api/show":
        model = json.loads(request.content)["model"]
        if model == "qwen3:8b":
            return httpx.Response(
                200,
                json={"details": {"family": "qwen3", "parameter_size": "8.2B", "quantization_level": "Q4_K_M"}},
            )
        return httpx.Response(404, json={"error": "model not found"})
    if path == "/api/chat":
        body = json.loads(request.content)
        if body.get("stream"):
            return httpx.Response(200, content=ndjson(*stream_lines_plain()))
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "volle Antwort"}, "eval_count": 3})
    return httpx.Response(404, json={"error": "not found"})


# --- Status & Modelle --------------------------------------------------------------


async def test_status_und_version():
    provider = make_provider(handler_ok)
    status = await provider.status()
    assert status.available and status.version == "0.40.16"
    await provider.aclose()


async def test_status_offline():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    provider = make_provider(handler)
    status = await provider.status()
    assert status.available is False
    assert "nicht erreichbar" in status.detail
    await provider.aclose()


async def test_list_models_und_has_model():
    provider = make_provider(handler_ok)
    models = await provider.list_models()
    assert [m.name for m in models] == ["qwen3:8b", "llama3.1:8b"]
    assert models[0].quantization == "Q4_K_M"
    assert await provider.has_model("qwen3:8b") is True
    assert await provider.has_model("mistral:7b") is False
    await provider.aclose()


async def test_model_info_fehlendes_modell():
    provider = make_provider(handler_ok)
    with pytest.raises(ModelNotFoundError):
        await provider.model_info("mistral:7b")
    await provider.aclose()


# --- Chat & Streaming --------------------------------------------------------------


async def test_stream_chat_parse_und_done():
    provider = make_provider(handler_ok)
    chunks = []
    async for chunk in provider.stream_chat(
        [ChatMessage(role="user", content="hi")], LLMOptions(), model="qwen3:8b"
    ):
        chunks.append(chunk)
    assert chunks[0].content == "Hallo "
    assert chunks[-1].done is True
    assert chunks[-1].meta["eval_count"] == 7
    await provider.aclose()


async def test_chat_payload_enthaelt_options_mapping():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            captured.update(json.loads(request.content))
            return httpx.Response(200, content=ndjson(*stream_lines_plain()))
        return httpx.Response(404)

    provider = make_provider(handler)
    options = LLMOptions(
        temperature=0.4, top_p=0.8, top_k=30, repeat_penalty=1.1, num_predict=512, num_ctx=4096
    )
    async for _ in provider.stream_chat(
        [ChatMessage(role="user", content="x")], options, model="qwen3:8b", keep_alive="5m"
    ):
        break

    assert captured["model"] == "qwen3:8b"
    assert captured["keep_alive"] == "5m"
    assert captured["stream"] is True
    assert captured["options"] == {
        "temperature": 0.4,
        "top_p": 0.8,
        "top_k": 30,
        "repeat_penalty": 1.1,
        "num_predict": 512,
        "num_ctx": 4096,
    }
    await provider.aclose()


async def test_chat_denktag_wird_standardmaessig_nicht_gesendet():
    """``think: false`` wird als Option übermittelt (Qwen3 ohne Reasoning)."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "ok"}, "done": True})

    provider = OllamaProvider("http://mock", OllamaDefaults(think=False))
    provider._client = httpx.AsyncClient(
        base_url=provider._base_url, transport=httpx.MockTransport(handler)
    )
    await provider.chat([ChatMessage(role="user", content="x")], LLMOptions(), model="qwen3:8b")
    assert captured["think"] is False

    # think=None → Parameter wird nicht gesendet (modellunabhängig).
    provider2 = OllamaProvider("http://mock", OllamaDefaults(think=None))
    provider2._client = httpx.AsyncClient(
        base_url=provider2._base_url, transport=httpx.MockTransport(handler)
    )
    captured.clear()
    await provider2.chat([ChatMessage(role="user", content="x")], LLMOptions(), model="qwen3:8b")
    assert "think" not in captured
    await provider.aclose()
    await provider2.aclose()


async def test_chat_nicht_streamend_stript_denkblock():
    def handler(request: httpx.Request) -> httpx.Response:
        content = (
            THINK_OPEN + "Innerer Gedanke, gehört nicht in die Antwort." + THINK_CLOSE + "Reine Antwort"
        )
        return httpx.Response(200, json={"message": {"content": content}, "eval_count": 5})

    provider = make_provider(handler)
    content, _meta = await provider.chat(
        [ChatMessage(role="user", content="x")], LLMOptions(), model="qwen3:8b"
    )
    assert content == "Reine Antwort"
    assert "Gedanke" not in content
    await provider.aclose()


async def test_stream_denkblock_entfernt_ueber_chunkgrenzen():
    # Denk-Tags über 3 Chunks verteilt: "<th", "ink>…</th", "ink>"
    lines = [
        {"message": {"content": "Erste "}, "done": False},
        {"message": {"content": "<th"}, "done": False},
        {"message": {"content": "ink>heimlich</th"}, "done": False},
        {"message": {"content": "ink>Zweite"}, "done": False},
        {"message": {"content": ""}, "done": True},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=ndjson(*lines))

    provider = make_provider(handler)
    collected = ""
    async for chunk in provider.stream_chat(
        [ChatMessage(role="user", content="x")], LLMOptions(), model="qwen3:8b"
    ):
        collected += chunk.content
        if chunk.done:
            break
    assert collected == "Erste Zweite"
    assert "heimlich" not in collected
    await provider.aclose()


async def test_stream_offener_denkblock_wird_entfernt():
    lines = [
        {"message": {"content": "Sichtbar "}, "done": False},
        {"message": {"content": THINK_OPEN + "nie sichtbar"}, "done": False},
        {"message": {"content": ""}, "done": True},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=ndjson(*lines))

    provider = make_provider(handler)
    collected = ""
    async for chunk in provider.stream_chat(
        [ChatMessage(role="user", content="x")], LLMOptions(), model="qwen3:8b"
    ):
        collected += chunk.content
        if chunk.done:
            break
    assert "nie sichtbar" not in collected
    await provider.aclose()


async def test_strip_think_blocks_hilfsfunktion():
    text = "A " + THINK_OPEN + "x" + THINK_CLOSE + " B"
    assert strip_think_blocks(text) == "A  B"
    assert strip_think_blocks("A " + THINK_OPEN + "x") == "A "


# --- Fehlerfälle --------------------------------------------------------------------


async def test_fehlendes_modell_beim_stream():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model 'x' not found"})

    provider = make_provider(handler)
    with pytest.raises(ModelNotFoundError):
        async for _ in provider.stream_chat(
            [ChatMessage(role="user", content="x")], LLMOptions(), model="qwen3:8b"
        ):
            pass
    await provider.aclose()


async def test_ollama_fehlerantwort_im_stream():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=ndjson({"error": "CUDA out of memory"}))

    provider = make_provider(handler)
    with pytest.raises(LLMResponseError):
        async for _ in provider.stream_chat(
            [ChatMessage(role="user", content="x")], LLMOptions(), model="qwen3:8b"
        ):
            pass
    await provider.aclose()


async def test_timeout_wird_uebersetzt():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("zu langsam")

    provider = make_provider(handler)
    with pytest.raises(LLMTimeoutError):
        await provider.chat([ChatMessage(role="user", content="x")], LLMOptions(), model="qwen3:8b")
    await provider.aclose()


async def test_verbindungsfehler_wird_uebersetzt():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    provider = make_provider(handler)
    with pytest.raises(ProviderConnectionError):
        await provider.list_models()
    await provider.aclose()


# --- Provider-Abstraktion / Registry --------------------------------------------------


def test_unbekannter_provider_wird_abgelehnt():
    with pytest.raises(ConfigurationError) as excinfo:
        create_provider("llamacpp", {})
    assert "ollama" in excinfo.value.detail["verfügbar"]


def test_ollama_aus_fabrik():
    provider = create_provider("ollama", {"base_url": "http://x:1234", "timeout": 30})
    assert isinstance(provider, OllamaProvider)
    assert provider.name == "ollama"


def test_eigener_provider_kann_registriert_werden():
    class MyProvider(LLMProvider):
        name = "myprovider"

        async def status(self):
            return ProviderStatus(available=True, version="1")

        async def list_models(self):
            return []

        async def model_info(self, model):
            raise ModelNotFoundError("kein Modell")

        async def has_model(self, model):
            return False

        def stream_chat(self, messages, options, *, model, keep_alive=None):
            async def gen():
                yield StreamChunk(content="ok", done=True)

            return gen()

        async def chat(self, messages, options, *, model, keep_alive=None):
            return "ok", {}

    register_provider(MyProvider.name, lambda cfg: MyProvider())
    assert "myprovider" in available_providers()
    provider = create_provider("myprovider", {})
    assert isinstance(provider, MyProvider)


def test_basisklasse_ist_abstrakt():
    with pytest.raises(TypeError):
        LLMProvider()  # type: ignore[abstract]
