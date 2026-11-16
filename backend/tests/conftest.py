"""Test-Konfiguration für ZENJI.

Alle Tests laufen ohne installiertes Sprachmodell und ohne echte SSD:

- ``zenji_env``        setzt die ZENJI-Umgebungsvariablen auf ein temporäres
                       Verzeichnis (kein Ersatzpfad im Produktivcode – nur
                       für Tests, wo ein SSD-Pfad simuliert wird).
- ``FakeProvider``     ersetzt Ollama (deterministische Antworten, Aufzeichnung).
- ``MockTransport``    simuliert die echte Ollama-HTTP-API für Providertests.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.core.exceptions import ModelNotFoundError, ProviderConnectionError, SearchProviderError
from app.engines.providers.base import (
    ChatMessage,
    LLMOptions,
    LLMProvider,
    ModelInfo,
    ProviderStatus,
    StreamChunk,
)
from app.main import create_app

FAKE_REPLY = "Guten Tag. Ich bin ZENJI, die Testantwort des FakeProviders."


class FakeProvider(LLMProvider):
    """Deterministischer Test-Provider ohne Netzwerk."""

    name = "fake"

    def __init__(
        self,
        *,
        available: bool = True,
        models: tuple[str, ...] = ("qwen3:8b",),
        reply: str = FAKE_REPLY,
    ) -> None:
        self.available = available
        self.models = models
        self.reply = reply
        self.chat_calls: list[dict[str, Any]] = []
        self.stream_calls: list[dict[str, Any]] = []

    async def status(self) -> ProviderStatus:
        if self.available:
            return ProviderStatus(available=True, version="fake-1.0.0")
        return ProviderStatus(available=False, detail="FakeProvider offline")

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name=m) for m in self.models]

    async def model_info(self, model: str) -> ModelInfo:
        if not self.available:
            raise RuntimeError("offline")
        if model not in self.models:
            raise ModelNotFoundError(f"Modell '{model}' ist in Ollama nicht vorhanden.")
        return ModelInfo(name=model, family="fake", parameter_size="8B", quantization="Q4_K_M")

    async def has_model(self, model: str) -> bool:
        return self.available and model in self.models

    def _record(self, messages: list[ChatMessage], options: LLMOptions, model: str, keep_alive: str | None, bucket: list) -> dict[str, Any]:
        record = {
            "model": model,
            "keep_alive": keep_alive,
            "options": options,
            "roles": [m.role for m in messages],
            "messages": [ChatMessage(role=m.role, content=m.content) for m in messages],
        }
        bucket.append(record)
        return record

    def stream_chat(
        self,
        messages: list[ChatMessage],
        options: LLMOptions,
        *,
        model: str,
        keep_alive: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        if not self.available:
            raise ProviderConnectionError(
                "FakeProvider ist offline (simulierte Ollama-Störung)."
            )
        record = self._record(messages, options, model, keep_alive, self.stream_calls)
        words = self.reply.split(" ")

        async def _gen() -> AsyncIterator[StreamChunk]:
            for index, word in enumerate(words):
                piece = word if index == len(words) - 1 else word + " "
                yield StreamChunk(content=piece)
            yield StreamChunk(done=True, meta={"eval_count": len(words)})

        return _gen()

    async def chat(
        self,
        messages: list[ChatMessage],
        options: LLMOptions,
        *,
        model: str,
        keep_alive: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        if not self.available:
            raise ProviderConnectionError(
                "FakeProvider ist offline (simulierte Ollama-Störung)."
            )
        self._record(messages, options, model, keep_alive, self.chat_calls)
        return self.reply, {"eval_count": len(self.reply.split())}


# --- Fixture-Helfer -----------------------------------------------------------


def build_settings(env: dict[str, str]) -> Settings:
    """Settings aus expliziten Umgebungsvariablen (kein .env-File)."""
    return Settings(**env)  # type: ignore[call-arg]


@pytest.fixture()
def zenji_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Simulierte SSD-Wurzel als temporärer Pfad; Umgebungsvariablen gesetzt.

    Der Pfad wird **nicht** angelegt – Tests entscheiden selbst (fehlende SSD
    vs. bereitgestellte SSD).
    """
    ssd_root = tmp_path / "ssd"
    monkeypatch.setenv("ZENJI_SSD_ROOT", str(ssd_root))
    monkeypatch.delenv("ZENJI_STORAGE_DIR", raising=False)
    monkeypatch.delenv("ZENJI_DB_PATH", raising=False)
    monkeypatch.delenv("ZENJI_LOG_DIR", raising=False)
    monkeypatch.setenv("ZENJI_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("ZENJI_OLLAMA_BASE_URL", "http://testserver:11434")
    monkeypatch.setenv("ZENJI_CORS_ORIGINS", "http://localhost:5173")
    # Explizite Defaults (unabhängig vom Rechnerzustand):
    monkeypatch.setenv("ZENJI_LLM__PROVIDER", "ollama")
    monkeypatch.setenv("ZENJI_LLM__MODEL", "qwen3:8b")
    monkeypatch.setenv("ZENJI_LLM__TEMPERATURE", "0.7")
    monkeypatch.setenv("ZENJI_LLM__TOP_P", "0.9")
    monkeypatch.setenv("ZENJI_LLM__TOP_K", "20")
    monkeypatch.setenv("ZENJI_LLM__REPEAT_PENALTY", "1.05")
    monkeypatch.setenv("ZENJI_LLM__NUM_PREDICT", "2048")
    monkeypatch.setenv("ZENJI_LLM__NUM_CTX", "8192")
    monkeypatch.setenv("ZENJI_LLM__STREAM", "true")
    return ssd_root


@pytest.fixture()
def make_ssd(zenji_env: Path) -> Callable[[], Path]:
    """Erstellt die simulierte SSD samt ZENJI-Struktur."""

    def _make() -> Path:
        zenji_env.mkdir(parents=True, exist_ok=True)
        for name in ("ZENJI", "models", "datasets", "backups", "environments", "logs"):
            (zenji_env / name).mkdir(exist_ok=True)
        return zenji_env

    return _make


def make_provider_factory(provider: FakeProvider) -> Callable[[str, dict], LLMProvider]:
    def _factory(name: str, config: dict[str, Any]) -> LLMProvider:
        return provider

    return _factory


@pytest.fixture()
def app_factory(zenji_env: Path):
    """Fabrik für App-Instanzen mit individuellen Optionen."""

    def _make(
        *,
        provider: LLMProvider | None = None,
        with_lifespan: bool = True,
    ):
        app = create_app(provider_factory=make_provider_factory(provider or FakeProvider()))
        return app

    return _make


@asynccontextmanager
async def open_app(app) -> AsyncIterator[Any]:
    """Startet den Lifespan der App (Schema-Erstellung etc.) für Tests."""
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture()
async def client(make_ssd, app_factory):
    """Laufende App (Lifespan gestartet) + HTTPX-Client (ASGI, ohne Port)."""
    make_ssd()
    app = app_factory()
    async with open_app(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, app


@pytest.fixture()
async def client_no_ssd(zenji_env, app_factory):
    """App ohne angelegte SSD (Pfad existiert nicht)."""
    app = app_factory()
    async with open_app(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, app


def parse_sse(raw: bytes) -> list[tuple[str, dict[str, Any]]]:
    """Zerlegt SSE-Bytes in (event, data)-Paare."""
    events: list[tuple[str, dict[str, Any]]] = []
    for block in raw.decode("utf-8").split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event = "message"
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: "):
                data_lines.append(line[len("data: "):])
        data = json.loads("\n".join(data_lines)) if data_lines else {}
        events.append((event, data))
    return events


class FakeSearchProvider:
    """Ersatz-Suchanbieter (offline deterministisch, Aufrufe aufgezeichnet)."""

    name = "searxng"

    def __init__(self, results: list[dict[str, Any]] | None = None, *, error: str | None = None):
        self.results = list(results or [])
        self.error = error
        self.calls: list[str] = []

    async def search(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        self.calls.append(query)
        if self.error:
            raise SearchProviderError(self.error)
        return [dict(entry) for entry in self.results[:limit]]

    async def status(self) -> dict[str, Any]:
        if self.error:
            return {"available": False, "detail": self.error}
        return {"available": True, "detail": "Fake-Provider verbunden."}


__all__ = [
    "FAKE_REPLY",
    "FakeProvider",
    "FakeSearchProvider",
    "build_settings",
    "make_provider_factory",
    "open_app",
    "parse_sse",
]
