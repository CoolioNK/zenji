"""Tests: Cloudflare-Workers-AI-Provider mit httpx.MockTransport (keine echte API)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import CloudflareDefaults, Settings
from app.core.exceptions import (
    ConfigurationError,
    LLMResponseError,
    ModelNotFoundError,
    ProviderConnectionError,
)
from app.engines.providers import available_providers, create_provider
from app.engines.providers.base import (
    THINK_CLOSE,
    THINK_OPEN,
    ChatMessage,
    LLMOptions,
    ProviderStatus,
)
from app.engines.providers.cloudflare import CloudflareProvider

ACCOUNT_ID = "a" * 32
API_TOKEN = "cf-test-token"
BASE = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}"

MODEL_FAST = "@cf/meta/llama-3.1-8b-instruct-fast"
MODEL_70B = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"


def make_provider(handler, *, account_id: str = ACCOUNT_ID, api_token: str = API_TOKEN) -> CloudflareProvider:
    provider = CloudflareProvider(
        account_id, api_token, CloudflareDefaults(timeout=5, connect_timeout=2)
    )
    if account_id:
        # Client exakt wie in _ensure_client() aufgebaut (inkl. Auth-Header).
        provider._client = httpx.AsyncClient(
            base_url=provider._base_url,
            timeout=httpx.Timeout(connect=2, read=5, write=5, pool=2),
            headers={"Authorization": f"Bearer {api_token}"},
            transport=httpx.MockTransport(handler),
        )
    return provider


def models_payload() -> dict:
    return {
        "success": True,
        "result": [
            {"name": MODEL_FAST, "task": {"name": "Text Generation"}},
            {
                "name": MODEL_70B,
                "tasks": [{"name": "Text Generation"}],
            },
            {"name": "@cf/baai/bge-m3", "task": {"name": "Embeddings"}},
            {"name": "@cf/stabilityai/sdxl", "task": {"name": "Text-to-Image"}},
        ],
        "result_info": {"page": 1, "per_page": 100, "count": 4, "total_count": 4},
    }


def sse_bytes(objects: list[dict], *, done: bool = True) -> bytes:
    parts: list[bytes] = []
    for obj in objects:
        parts.append(b"data: " + json.dumps(obj).encode() + b"\n\n")
    if done:
        parts.append(b"data: [DONE]\n\n")
    return b"".join(parts)


def stream_objects() -> list[dict]:
    return [
        {"response": "Hallo "},
        {"response": "Welt"},
        {"response": "", "usage": {"prompt_tokens": 3, "completion_tokens": 2}},
    ]


def handler_ok(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/ai/models/search"):
        assert request.headers.get("Authorization") == f"Bearer {API_TOKEN}"
        return httpx.Response(200, json=models_payload())
    if "/ai/run/" in path:
        body = json.loads(request.content)
        if body.get("stream"):
            return httpx.Response(
                200, content=sse_bytes(stream_objects()), headers={"content-type": "text/event-stream"}
            )
        model = path.rsplit("/ai/run/", 1)[1]
        if model == MODEL_FAST:
            return httpx.Response(
                200,
                json={
                    "result": {
                        "response": "volle Antwort",
                        "usage": {"prompt_tokens": 5, "completion_tokens": 2},
                    },
                    "success": True,
                    "errors": [],
                },
            )
        return httpx.Response(
            404,
            json={
                "result": None,
                "success": False,
                "errors": [{"code": 7000, "message": "no route for that model"}],
            },
        )
    return httpx.Response(404, json={"errors": [{"message": "not found"}]})


# --- Status & Modelle --------------------------------------------------------------


async def test_status_und_version():
    provider = make_provider(handler_ok)
    status = await provider.status()
    assert status.available and status.version == "Workers AI"
    await provider.aclose()


async def test_status_ohne_zugangsdaten():
    provider = make_provider(lambda request: httpx.Response(200, json={}), account_id="", api_token="")
    status = await provider.status()
    assert status.available is False
    assert "ZENJI_CLOUDFLARE_ACCOUNT_ID" in status.detail
    assert "ZENJI_CLOUDFLARE_API_TOKEN" in status.detail


async def test_status_token_abgelehnt():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"errors": [{"message": "Authentication error"}]})

    provider = make_provider(handler)
    status = await provider.status()
    assert status.available is False
    assert "Token" in status.detail
    await provider.aclose()


async def test_status_offline():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    provider = make_provider(handler)
    status = await provider.status()
    assert status.available is False
    assert "nicht erreichbar" in status.detail
    await provider.aclose()


async def test_list_models_filtert_textgenerierung():
    provider = make_provider(handler_ok)
    models = await provider.list_models()
    names = [m.name for m in models]
    assert MODEL_FAST in names and MODEL_70B in names
    # Embedding-/Bild-Modelle sind nicht chat-tauglich und werden gefiltert.
    assert "@cf/baai/bge-m3" not in names
    assert "@cf/stabilityai/sdxl" not in names
    llama = next(m for m in models if m.name == MODEL_FAST)
    assert llama.family == "meta"
    assert llama.parameter_size == "8B"
    assert llama.quantization is None
    big = next(m for m in models if m.name == MODEL_70B)
    assert big.quantization == "fp8"
    assert await provider.has_model(MODEL_FAST) is True
    assert await provider.has_model(MODEL_70B) is True
    assert await provider.has_model("qwen3:8b") is False
    await provider.aclose()


# --- Chat --------------------------------------------------------------------------


def _chat_messages() -> list[ChatMessage]:
    return [ChatMessage(role="system", content="Du bist ZENJI."), ChatMessage(role="user", content="Hallo")]


async def test_chat_ohne_stream():
    provider = make_provider(handler_ok)
    content, meta = await provider.chat(
        _chat_messages(), LLMOptions(num_predict=512), model=MODEL_FAST
    )
    assert content == "volle Antwort"
    assert meta["usage"]["completion_tokens"] == 2
    await provider.aclose()


async def test_chat_payload_sendet_nur_unterstuetzte_parameter():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["path"] = request.url.path
        return httpx.Response(200, json={"result": {"response": "ok"}, "success": True, "errors": []})

    provider = make_provider(handler)
    await provider.chat(_chat_messages(), LLMOptions(num_predict=777), model=MODEL_FAST)
    body = captured["body"]
    assert body["stream"] is False
    assert body["max_tokens"] == 777
    assert body["temperature"] == LLMOptions().temperature
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    # Ollama-spezifische Felder gehören nicht in den Cloudflare-Payload.
    assert "num_ctx" not in body
    assert "repeat_penalty" not in body
    assert "keep_alive" not in body
    # Das Modell steckt im Pfad, nicht im Body.
    assert "model" not in body
    assert captured["path"].endswith(f"/ai/run/{MODEL_FAST}")
    assert captured["path"].startswith(f"/client/v4/accounts/{ACCOUNT_ID}/")
    await provider.aclose()


async def test_chat_denkfilter_aktiv():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "result": {"response": THINK_OPEN + "Denken." + THINK_CLOSE + "Sichtbar."},
                "success": True,
                "errors": [],
            },
        )

    provider = make_provider(handler)
    content, _ = await provider.chat(_chat_messages(), LLMOptions(), model=MODEL_FAST)
    assert content == "Sichtbar."
    await provider.aclose()


async def test_stream_chat_liefert_chunks_und_done():
    provider = make_provider(handler_ok)
    chunks = [
        chunk
        async for chunk in provider.stream_chat(
            _chat_messages(), LLMOptions(), model=MODEL_FAST, keep_alive="10m"
        )
    ]
    assert "".join(c.content for c in chunks) == "Hallo Welt"
    assert chunks[-1].done is True
    assert chunks[-1].meta["usage"]["prompt_tokens"] == 3
    assert all(not c.done for c in chunks[:-1])
    await provider.aclose()


async def test_stream_chat_endet_ohne_done_marker_trotzdem_mit_done():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=sse_bytes([{"response": "Hallo"}], done=False),
            headers={"content-type": "text/event-stream"},
        )

    provider = make_provider(handler)
    chunks = [
        chunk async for chunk in provider.stream_chat(_chat_messages(), LLMOptions(), model=MODEL_FAST)
    ]
    assert "".join(c.content for c in chunks) == "Hallo"
    assert chunks[-1].done is True
    await provider.aclose()


# --- Fehlerbehandlung ----------------------------------------------------------------


async def test_chat_modell_nicht_gefunden_404():
    provider = make_provider(handler_ok)
    with pytest.raises(ModelNotFoundError):
        await provider.chat(_chat_messages(), LLMOptions(), model=MODEL_70B)
    await provider.aclose()


async def test_chat_token_fehler_401():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"errors": [{"message": "Authentication error"}]})

    provider = make_provider(handler)
    with pytest.raises(ProviderConnectionError) as excinfo:
        await provider.chat(_chat_messages(), LLMOptions(), model=MODEL_FAST)
    assert excinfo.value.provider == "cloudflare"
    assert excinfo.value.code == "CLOUDFLARE_UNAVAILABLE"
    await provider.aclose()


async def test_chat_fehlerantwort_400():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"result": None, "success": False, "errors": [{"message": "invalid input"}]}
        )

    provider = make_provider(handler)
    with pytest.raises(LLMResponseError) as excinfo:
        await provider.chat(_chat_messages(), LLMOptions(), model=MODEL_FAST)
    assert "invalid input" in str(excinfo.value.message)
    await provider.aclose()


async def test_stream_sse_fehlerfeld_wird_gehoben():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=sse_bytes([{"error": "model overloaded"}], done=False),
            headers={"content-type": "text/event-stream"},
        )

    provider = make_provider(handler)
    with pytest.raises(LLMResponseError):
        _ = [chunk async for chunk in provider.stream_chat(_chat_messages(), LLMOptions(), model=MODEL_FAST)]
    await provider.aclose()


async def test_chat_ohne_zugangsdaten_configuration_error():
    provider = make_provider(handler_ok, account_id="", api_token="")
    with pytest.raises(ConfigurationError):
        await provider.chat(_chat_messages(), LLMOptions(), model=MODEL_FAST)


# --- Fabrik & Konfiguration ----------------------------------------------------------


def test_cloudflare_aus_fabrik():
    provider = create_provider(
        "cloudflare",
        {"account_id": ACCOUNT_ID, "api_token": API_TOKEN, "timeout": 30, "connect_timeout": 3},
    )
    assert isinstance(provider, CloudflareProvider)
    assert provider.name == "cloudflare"
    assert provider._config.timeout == 30
    assert "cloudflare" in available_providers()
    assert "ollama" in available_providers()


def test_settings_cloudflare_felder():
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        llm={"provider": "cloudflare", "model": MODEL_FAST},
        cloudflare_account_id=ACCOUNT_ID.upper(),
        cloudflare_api_token="  token  ",
    )
    assert settings.llm.provider == "cloudflare"
    assert settings.cloudflare_account_id == ACCOUNT_ID  # normalisiert (klein)
    assert settings.cloudflare_api_token == "token"
    assert settings.cloudflare.strip_think is True


def test_settings_cloudflare_konto_id_ungueltig():
    with pytest.raises(ValueError):
        Settings(_env_file=None, cloudflare_account_id="nicht-hex")  # type: ignore[call-arg]


async def test_app_mit_cloudflare_settings_erstellt_cloudflare_provider(tmp_path):
    from app.main import create_app

    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        ssd_root=tmp_path,
        llm={"provider": "cloudflare", "model": MODEL_FAST},
        cloudflare_account_id=ACCOUNT_ID,
        cloudflare_api_token=API_TOKEN,
    )
    app = create_app(settings=settings)
    provider = app.state.llm_engine.provider
    assert isinstance(provider, CloudflareProvider)
    assert provider.name == "cloudflare"
    assert provider._base_url == BASE
    await provider.aclose()
