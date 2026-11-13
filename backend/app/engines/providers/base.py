"""Provider-Abstraktion für Sprachmodelle.

ZENJI koppelt sich **nicht** fest an Ollama.  Jeder Anbieter implementiert das
Protokoll aus :mod:`app.engines.providers.base`.  Phase 1 liefert Ollama;
weitere Provider (z. B. llama.cpp, LM Studio, OpenAI-kompatible Endpunkte)
werden in :mod:`app.engines.providers` registriert.

Die Engine kennt nur die Abstraktion – niemals konkrete Anbieter-Details.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

from app.core.exceptions import ConfigurationError, LLMError

THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


@dataclass(slots=True)
class ChatMessage:
    """Eine Nachricht im LLM-Dialog (Rolle: system/user/assistant)."""

    role: str
    content: str


@dataclass(slots=True)
class LLMOptions:
    """Anbieterunabhängige Parameter eines LLM-Aufrufs."""

    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 20
    repeat_penalty: float = 1.05
    num_predict: int = 2048
    num_ctx: int = 8192
    stop: list[str] = field(default_factory=list)


@dataclass(slots=True)
class StreamChunk:
    """Ein Teil einer gestreamten Antwort."""

    content: str = ""
    done: bool = False
    thinking: str = ""
    meta: dict[str, Any] | None = None


@dataclass(slots=True)
class ModelInfo:
    """Beschreibung eines verfügbaren Modells."""

    name: str
    family: str | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    size_bytes: int | None = None
    modified_at: datetime | None = None


@dataclass(slots=True)
class ProviderStatus:
    """Ergebnis eines Verfügbarkeitschecks."""

    available: bool
    version: str | None = None
    detail: str | None = None


class LLMProvider(ABC):
    """Protokoll, das jeder Modell-Provider implementieren muss.

    Der Provider ist ausschließlich für Kommunikation zuständig – ohne
    UI-, Datenbank- oder Policy-Logik (Trennung gemäß Architektur).
    """

    #: Kurzname, unter dem der Provider in der Konfiguration gewählt wird.
    name: ClassVar[str] = "abstract"

    @abstractmethod
    async def status(self) -> ProviderStatus:
        """Erreichbarkeit und Version des Providers prüfen."""

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """Alle lokal verfügbaren Modelle auflisten."""

    @abstractmethod
    async def model_info(self, model: str) -> ModelInfo:
        """Details zu einem Modell; :class:`ModelNotFoundError` wenn fehlend."""

    @abstractmethod
    async def has_model(self, model: str) -> bool:
        """True, wenn das Modell geladen/verfügbar ist."""

    @abstractmethod
    def stream_chat(
        self,
        messages: list[ChatMessage],
        options: LLMOptions,
        *,
        model: str,
        keep_alive: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Antwort als Stream ausliefern."""

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        options: LLMOptions,
        *,
        model: str,
        keep_alive: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Vollständige Antwort liefern (Inhalt + Metadaten)."""

    async def aclose(self) -> None:
        """Optionale Ressourcenfreigabe (HTTP-Clients etc.)."""


class ThinkFilter:
    """Entfernt ``<think>…</think>``-Segmente aus einem Content-Stream.

    Qwen3-artige Modelle können Reasoning-Ausgaben in den Text mischen.
    Der Filter ist zustandsbehaftet und funktioniert über Chunk-Grenzen hinweg
    (auch wenn die Tags selbst über mehrere Chunks verteilt eintreffen).
    Aktivierbar per Provider-Konfiguration (``strip_think``).
    """

    OPEN = THINK_OPEN
    CLOSE = THINK_CLOSE

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self._buffer = ""
        self._inside = False

    def feed(self, text: str) -> str:
        """Nimmt einen Chunk an, gibt den sichtbaren Anteil zurück."""
        if not self.enabled:
            return text
        self._buffer += text
        out: list[str] = []
        while True:
            if self._inside:
                end = self._buffer.find(self.CLOSE)
                if end == -1:
                    # Noch im Denkblock; evtl. Beginn des Schließ-Tags behalten.
                    keep = _partial_len(self._buffer, self.CLOSE)
                    self._buffer = self._buffer[len(self._buffer) - keep:] if keep else ""
                    return "".join(out)
                self._buffer = self._buffer[end + len(self.CLOSE):]
                self._inside = False
                continue
            start = self._buffer.find(self.OPEN)
            if start == -1:
                # Möglicherweise fragmentierten Öffnungs-Tag zurückhalten.
                keep = _partial_len(self._buffer, self.OPEN)
                flush = len(self._buffer) - keep
                if flush > 0:
                    out.append(self._buffer[:flush])
                    self._buffer = self._buffer[flush:]
                return "".join(out)
            out.append(self._buffer[:start])
            self._buffer = self._buffer[start + len(self.OPEN):]
            self._inside = True

    def flush(self) -> str:
        """Am Stream-Ende Restbuffer freigeben (offener Denkblock = nichts)."""
        rest = self._buffer
        self._buffer = ""
        if self._inside:
            return ""
        return rest


def _partial_len(text: str, tag: str) -> int:
    """Länge eines Suffixes von ``text``, das ein fragmentiertes ``tag`` sein könnte."""
    for k in range(min(len(text), len(tag) - 1), 0, -1):
        if tag[:k] == text[-k:]:
            return k
    return 0


def strip_think_blocks(text: str) -> str:
    """Einmaliges Entfernen aller Denkblöcke (für Nicht-Streaming-Pfade).

    Ein ungeschlossener Denkblock entfernt inklusive seines gesamten Restes.
    """
    cleaned = _THINK_RE.sub("", text)
    idx = cleaned.find(THINK_OPEN)
    if idx != -1:
        cleaned = cleaned[:idx]
    return cleaned


def ensure_valid_options(options: LLMOptions) -> None:
    """Verteidigt den Provider vor offensichtlich unsinnigen Parametern."""
    if options.temperature < 0 or options.temperature > 2:
        raise ConfigurationError("temperature muss zwischen 0 und 2 liegen")
    if not 0 < options.top_p <= 1:
        raise ConfigurationError("top_p muss in (0, 1] liegen")
    if options.top_k < 1:
        raise ConfigurationError("top_k muss >= 1 sein")
    if options.num_predict < 1:
        raise ConfigurationError("num_predict muss >= 1 sein")


__all__ = [
    "ChatMessage",
    "LLMError",
    "LLMOptions",
    "LLMProvider",
    "ModelInfo",
    "ProviderStatus",
    "StreamChunk",
    "ThinkFilter",
    "strip_think_blocks",
]
