"""Ollama-Provider: HTTP-Anbindung über die Ollama-REST-API.

Implementiert :class:`app.engines.providers.base.LLMProvider` ausschließlich
mit der Aspekt „Kommunikation“ – keine Geschäftslogik.

Streaming: Ollama liefert pro Chunk eine NDJSON-Zeile.  Diese wird
inkrementell in :class:`StreamChunk` übersetzt.  Zeitüberschreitung gilt
pro Chunk (Read-Timeout), nicht für die gesamte Antwort.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx

from app.core.config import OllamaDefaults
from app.core.exceptions import (
    LLMResponseError,
    LLMTimeoutError,
    ModelNotFoundError,
    ProviderConnectionError,
)
from app.core.logging import get_logger
from app.engines.providers.base import (
    ChatMessage,
    LLMOptions,
    LLMProvider,
    ModelInfo,
    ProviderStatus,
    StreamChunk,
    ThinkFilter,
    ensure_valid_options,
    strip_think_blocks,
)

log = get_logger("provider.ollama")


class OllamaProvider(LLMProvider):
    """Provider für einen lokalen oder entfernten Ollama-Server."""

    name = "ollama"

    def __init__(self, base_url: str, config: OllamaDefaults | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._config = config or OllamaDefaults()
        self._client: httpx.AsyncClient | None = None

    # --- HTTP-Lifecycle --------------------------------------------------------
    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(
                connect=self._config.connect_timeout,
                read=self._config.timeout,
                write=self._config.timeout,
                pool=self._config.connect_timeout,
            )
            self._client = httpx.AsyncClient(base_url=self._base_url, timeout=timeout)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # --- Status & Modelle --------------------------------------------------------
    async def status(self) -> ProviderStatus:
        try:
            response = await self._ensure_client().get("/api/version", timeout=3.0)
            response.raise_for_status()
            version = response.json().get("version")
            return ProviderStatus(available=True, version=version)
        except httpx.TimeoutException:
            return ProviderStatus(available=False, detail="Zeitüberschreitung bei Ollama-Anfrage")
        except httpx.HTTPError as exc:
            return ProviderStatus(available=False, detail=f"Ollama nicht erreichbar ({exc.__class__.__name__})")
        except Exception as exc:  # noqa: BLE001 – Status darf nie crashen
            return ProviderStatus(available=False, detail=str(exc))

    async def list_models(self) -> list[ModelInfo]:
        try:
            response = await self._ensure_client().get("/api/tags")
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("Ollama antwortet nicht (Zeitüberschreitung).") from exc
        except httpx.HTTPError as exc:
            raise ProviderConnectionError(
                f"Ollama ist nicht erreichbar unter {self._base_url}: {exc.__class__.__name__}"
            ) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise LLMResponseError("Ollama lieferte keine gültige Modelliste.") from exc
        return [self._parse_model_entry(entry) for entry in payload.get("models", [])]

    async def model_info(self, model: str) -> ModelInfo:
        try:
            response = await self._ensure_client().post("/api/show", json={"model": model})
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("Ollama antwortet nicht (Zeitüberschreitung).") from exc
        except httpx.HTTPError as exc:
            raise ProviderConnectionError(
                f"Ollama ist nicht erreichbar unter {self._base_url}: {exc.__class__.__name__}"
            ) from exc
        if response.status_code == 404:
            raise ModelNotFoundError(
                f"Modell '{model}' ist in Ollama nicht vorhanden.",
                detail=f"Tipp: 'ollama pull {model}' ausführen (Gewichte landen auf der SSD, siehe STORAGE.md).",
            )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise LLMResponseError(f"Ungültige Modellinformationen für '{model}'.") from exc
        details = payload.get("details", {})
        return ModelInfo(
            name=model,
            family=details.get("family"),
            parameter_size=details.get("parameter_size"),
            quantization=details.get("quantization_level"),
            modified_at=self._parse_datetime(payload.get("modified_at")),
        )

    async def has_model(self, model: str) -> bool:
        try:
            models = await self.list_models()
        except ProviderConnectionError:
            raise
        except LLMError:
            return False
        return any(m.name == model for m in models)

    # --- Chat ----------------------------------------------------------------------
    def _build_payload(
        self,
        messages: list[ChatMessage],
        options: LLMOptions,
        *,
        model: str,
        stream: bool,
        keep_alive: str | None,
        think: bool | None,
    ) -> dict[str, Any]:
        ensure_valid_options(options)
        ollama_options: dict[str, Any] = {
            "temperature": options.temperature,
            "top_p": options.top_p,
            "top_k": options.top_k,
            "repeat_penalty": options.repeat_penalty,
            "num_predict": options.num_predict,
            "num_ctx": options.num_ctx,
        }
        if options.stop:
            ollama_options["stop"] = options.stop

        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": stream,
            "options": ollama_options,
        }
        payload["keep_alive"] = keep_alive or self._config.keep_alive
        # Qwen3 & Co.: Reasoning gezielt steuern (None = Parameter nicht senden).
        if think is not None:
            payload["think"] = think
        return payload

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        options: LLMOptions,
        *,
        model: str,
        keep_alive: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        payload = self._build_payload(
            messages, options, model=model, stream=True, keep_alive=keep_alive, think=self._config.think
        )
        think_filter = ThinkFilter(self._config.strip_think)
        try:
            client = self._ensure_client()
            async with client.stream("POST", "/api/chat", json=payload) as response:
                if response.status_code == 404:
                    raise ModelNotFoundError(
                        f"Modell '{model}' ist in Ollama nicht vorhanden.",
                        detail=f"Tipp: 'ollama pull {model}' ausführen.",
                    )
                if response.status_code >= 400:
                    body = await response.aread()
                    raise LLMResponseError(
                        f"Ollama-Fehler (HTTP {response.status_code}): "
                        f"{self._error_message(body)}"
                    )
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = self._parse_stream_line(line, think_filter)
                    if chunk is None:
                        continue
                    yield chunk
                    if chunk.done:
                        break
            trailing = think_filter.flush()
            if trailing:
                yield StreamChunk(content=trailing)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                "Zeitüberschreitung beim Streamen der Modellantwort."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderConnectionError(
                f"Verbindung zu Ollama unter {self._base_url} fehlgeschlagen: "
                f"{exc.__class__.__name__}"
            ) from exc

    async def chat(
        self,
        messages: list[ChatMessage],
        options: LLMOptions,
        *,
        model: str,
        keep_alive: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        payload = self._build_payload(
            messages, options, model=model, stream=False, keep_alive=keep_alive, think=self._config.think
        )
        try:
            response = await self._ensure_client().post("/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("Zeitüberschreitung bei der Modellanfrage.") from exc
        except httpx.HTTPError as exc:
            raise ProviderConnectionError(
                f"Verbindung zu Ollama unter {self._base_url} fehlgeschlagen: "
                f"{exc.__class__.__name__}"
            ) from exc
        if response.status_code == 404:
            raise ModelNotFoundError(
                f"Modell '{model}' ist in Ollama nicht vorhanden.",
                detail=f"Tipp: 'ollama pull {model}' ausführen.",
            )
        if response.status_code >= 400:
            raise LLMResponseError(
                f"Ollama-Fehler (HTTP {response.status_code}): {self._error_message(response.content)}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMResponseError("Ollama lieferte keine gültige Chat-Antwort.") from exc
        content = data.get("message", {}).get("content", "")
        if self._config.strip_think:
            content = strip_think_blocks(content)
        meta = {
            key: data[key]
            for key in ("total_duration", "eval_count", "eval_duration", "prompt_eval_count")
            if key in data
        }
        return content, meta

    # --- Hilfsfunktionen ------------------------------------------------------------
    def _parse_stream_line(self, line: str, think_filter: ThinkFilter) -> StreamChunk | None:
        try:
            data = json.loads(line)
        except ValueError:
            log.warning("Ungültige NDJSON-Zeile von Ollama ignoriert: %.120s", line)
            return None
        if "error" in data:
            raise LLMResponseError(f"Ollama-Fehler: {data['error']}")
        message = data.get("message", {})
        content = message.get("content", "") or ""
        visible = think_filter.feed(content)
        return StreamChunk(
            content=visible,
            thinking=message.get("thinking", "") or "",
            done=bool(data.get("done", False)),
            meta={k: data[k] for k in ("total_duration", "eval_count") if k in data} if data.get("done") else None,
        )

    @staticmethod
    def _error_message(body: bytes | str) -> str:
        try:
            data = json.loads(body)
            return str(data.get("error", body))
        except ValueError:
            return (body if isinstance(body, str) else body.decode("utf-8", "replace"))[:200]

    @staticmethod
    def _parse_model_entry(entry: dict[str, Any]) -> ModelInfo:
        details = entry.get("details", {}) or {}
        modified = OllamaProvider._parse_datetime(entry.get("modified_at"))
        return ModelInfo(
            name=entry.get("name", ""),
            family=details.get("family"),
            parameter_size=details.get("parameter_size"),
            quantization=details.get("quantization_level"),
            size_bytes=entry.get("size"),
            modified_at=modified,
        )

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value or not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
