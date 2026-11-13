"""LLM Engine – die schlanke Kommunikationsschicht zum Sprachmodell.

Verantwortung (bewusst eng gehalten):

- Verbindung zum konfigurierten Provider
- Modellstatus / Modellinformationen
- Nachrichten senden, Antworten empfangen (komplett oder als Stream)

Keine UI-Logik, keine Datenbankzugriffe, keine Policy-Entscheidungen.
Der Chat-Service bestimmt, *was* gefragt wird; die Engine bestimmt *wie*.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.core.logging import get_logger
from app.engines.model_manager import ModelManager
from app.engines.providers.base import (
    ChatMessage,
    LLMOptions,
    LLMProvider,
    ModelInfo,
    ProviderStatus,
    StreamChunk,
)

log = get_logger("llm_engine")


class LLMEngine:
    """Fassade über dem aktiven Provider. Modellunabhängig einsetzbar."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider
        self._model_manager = ModelManager(provider)

    # --- Provider & Modell -------------------------------------------------------
    @property
    def provider(self) -> LLMProvider:
        return self._provider

    @property
    def model_manager(self) -> ModelManager:
        return self._model_manager

    async def provider_status(self) -> ProviderStatus:
        return await self._provider.status()

    async def model_info(self, model: str) -> ModelInfo:
        return await self._model_manager.info(model)

    async def list_models(self) -> list[ModelInfo]:
        return await self._model_manager.list_models()

    async def ensure_model_available(self, model: str) -> None:
        await self._model_manager.ensure_available(model)

    # --- Generierung ---------------------------------------------------------------
    async def generate(
        self,
        messages: list[ChatMessage],
        options: LLMOptions,
        *,
        model: str,
        keep_alive: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Komplette Antwort abrufen (nicht-streamend)."""
        log.debug("generate: model=%s, %d Nachrichten", model, len(messages))
        return await self._provider.chat(messages, options, model=model, keep_alive=keep_alive)

    def stream(
        self,
        messages: list[ChatMessage],
        options: LLMOptions,
        *,
        model: str,
        keep_alive: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Antwort als Stream abrufen."""
        log.debug("stream: model=%s, %d Nachrichten", model, len(messages))
        return self._provider.stream_chat(messages, options, model=model, keep_alive=keep_alive)

    async def aclose(self) -> None:
        await self._provider.aclose()
