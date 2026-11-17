"""Cloudflare Workers AI: HTTP-Anbindung über die Cloudflare-REST-API.

Implementiert :class:`app.engines.providers.base.LLMProvider` – wie der
Ollama-Provider ausschließlich mit dem Aspekt „Kommunikation".  Kein lokaler
Modellserver nötig: Das Modell läuft in der Cloudflare-Cloud (Free-Plan
möglich, täglich 10.000 Neuronen).

REST-Endpunkte (mit ``Authorization: Bearer <api_token>``):

- Modellliste:  ``GET  {base}/ai/models/search``
- Inferenz:     ``POST {base}/ai/run/{model}``
                (z. B. ``…/ai/run/@cf/meta/llama-3.1-8b-instruct-fast``)

Streaming: Workers AI antwortet mit Server-Sent-Events – pro Chunk eine
``data: {"response": "…"}-Zeile, Ende via ``data: [DONE]``.  Zeitüberschreitung
gilt pro Chunk (Read-Timeout), nicht für die gesamte Antwort.

Parameter-Abbildung: ``num_predict`` → ``max_tokens``; ``temperature``,
``top_p`` und ``stop`` werden 1:1 übernommen.  ``num_ctx``, ``repeat_penalty``
und ``top_k`` haben in Workers AI kein Pendant und werden absichtlich **nicht**
gesendet (unbekannte Felder können eine Validierungsablehnung auslösen).
``keep_alive`` ist ein Ollama-Konzept und wird hier ignoriert.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import CloudflareDefaults
from app.core.exceptions import (
    ConfigurationError,
    LLMError,
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

log = get_logger("provider.cloudflare")

_TEXT_TASK_MARKERS = ("text generation", "text-generation")
_QUANT_RE = re.compile(r"(fp8|fp16|int8|int4|awq|4bit|8bit)", re.IGNORECASE)
_PARAM_RE = re.compile(r"(\d+(?:\.\d+)?)[bB](?=[-\s/]|$)")

#: Der Modellkatalog ändert sich selten – ohne Cache würde jede Chat-Nachricht
#: einen paginierten Katalog-Fetch auslösen (auf dem Render-Free-Tier mit
#: 0.1 CPU mehrere Sekunden reine Wartezeit).
_MODELS_CACHE_TTL = 300.0


class CloudflareProvider(LLMProvider):
    """Provider für Cloudflare Workers AI (Modell-Inferenz in der Cloud)."""

    name = "cloudflare"

    def __init__(
        self,
        account_id: str,
        api_token: str,
        config: CloudflareDefaults | None = None,
    ) -> None:
        self._account_id = account_id.strip()
        self._api_token = api_token.strip()
        self._config = config or CloudflareDefaults()
        self._client: httpx.AsyncClient | None = None
        self._models_cache: list[ModelInfo] | None = None
        self._models_cached_at: float = 0.0
        # Bewusst als Attribut `_base_url` (wie beim Ollama-Provider), damit
        # der Health-Endpoint den Endpunkt anzeigen kann.
        self._base_url = (
            f"https://api.cloudflare.com/client/v4/accounts/{self._account_id}"
            if self._account_id
            else ""
        )

    # --- Konfiguration ----------------------------------------------------------
    def _missing_credentials(self) -> str:
        missing: list[str] = []
        if not self._account_id:
            missing.append("ZENJI_CLOUDFLARE_ACCOUNT_ID")
        if not self._api_token:
            missing.append("ZENJI_CLOUDFLARE_API_TOKEN")
        return " und ".join(missing)

    def _require_credentials(self) -> None:
        missing = self._missing_credentials()
        if missing:
            raise ConfigurationError(
                f"Cloudflare Workers AI ist nicht konfiguriert: {missing} fehlt in backend/.env."
            )

    # --- HTTP-Lifecycle ----------------------------------------------------------
    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(
                connect=self._config.connect_timeout,
                read=self._config.timeout,
                write=self._config.timeout,
                pool=self._config.connect_timeout,
            )
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=timeout,
                headers={"Authorization": f"Bearer {self._api_token}"},
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # --- Status & Modelle --------------------------------------------------------
    async def status(self) -> ProviderStatus:
        missing = self._missing_credentials()
        if missing:
            return ProviderStatus(
                available=False,
                detail=f"Cloudflare Workers AI ist nicht konfiguriert: {missing} fehlt.",
            )
        try:
            response = await self._ensure_client().get(
                "/ai/models/search", params={"per_page": 1}, timeout=5.0
            )
        except httpx.TimeoutException:
            return ProviderStatus(available=False, detail="Zeitüberschreitung bei Cloudflare-Anfrage")
        except httpx.HTTPError as exc:
            return ProviderStatus(
                available=False, detail=f"Cloudflare-API nicht erreichbar ({exc.__class__.__name__})"
            )
        except Exception as exc:  # noqa: BLE001 – Status darf nie crashen
            return ProviderStatus(available=False, detail=str(exc))
        if response.status_code in (401, 403):
            return ProviderStatus(
                available=False,
                detail="Cloudflare hat den API-Token abgelehnt (HTTP 401/403) – Token prüfen.",
            )
        if response.status_code >= 400:
            return ProviderStatus(
                available=False,
                detail=f"Cloudflare-API-Fehler (HTTP {response.status_code})",
            )
        return ProviderStatus(available=True, version="Workers AI")

    async def list_models(self) -> list[ModelInfo]:
        """Text-Generierungs-Modelle des Cloudflare-Katalogs (paginiert).

        Ergebnis wird 5 Minuten gecacht — der Katalog ändert sich selten und
        der Fetch ist teuer (auf schwacher CPU mehrere Sekunden pro Turn).
        """
        self._require_credentials()
        now = time.monotonic()
        if self._models_cache is not None and now - self._models_cached_at < _MODELS_CACHE_TTL:
            return self._models_cache
        models: dict[str, ModelInfo] = {}
        page = 1
        collected = 0
        total: int | None = None
        while page <= 5:
            try:
                response = await self._ensure_client().get(
                    "/ai/models/search", params={"per_page": 100, "page": page}
                )
            except httpx.TimeoutException as exc:
                raise LLMTimeoutError("Cloudflare antwortet nicht (Zeitüberschreitung).") from exc
            except httpx.HTTPError as exc:
                raise ProviderConnectionError(
                    f"Cloudflare-API ist nicht erreichbar unter {self._base_url}: "
                    f"{exc.__class__.__name__}",
                    provider=self.name,
                ) from exc
            await self._raise_for_status(response)
            try:
                data = response.json()
            except ValueError as exc:
                raise LLMResponseError("Cloudflare lieferte keine gültige Modelliste.") from exc
            results = data.get("result") or []
            collected += len(results)
            for entry in results:
                info = self._parse_model_entry(entry)
                if info is not None:
                    models[info.name] = info
            info_block = data.get("result_info") or {}
            total = info_block.get("total_count", total)
            if not results or (total is not None and collected >= total):
                break
            page += 1
        self._models_cache = list(models.values())
        self._models_cached_at = time.monotonic()
        return self._models_cache

    async def model_info(self, model: str) -> ModelInfo:
        models = await self.list_models()
        for info in models:
            if info.name == model:
                return info
        raise ModelNotFoundError(
            f"Modell '{model}' ist bei Cloudflare Workers AI nicht vorhanden.",
            detail="Verfügbare Modelle: GET /api/models bzw. Cloudflare-Modellkatalog "
            "(https://developers.cloudflare.com/workers-ai/).",
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
    ) -> dict[str, Any]:
        ensure_valid_options(options)
        payload: dict[str, Any] = {
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": stream,
            "temperature": options.temperature,
            "top_p": options.top_p,
            "max_tokens": options.num_predict,
        }
        if options.stop:
            payload["stop"] = options.stop
        return payload

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        options: LLMOptions,
        *,
        model: str,
        keep_alive: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self._require_credentials()
        del keep_alive  # Ollama-Konzept; in Workers AI ohne Funktion.
        payload = self._build_payload(messages, options, model=model, stream=True)
        think_filter = ThinkFilter(self._config.strip_think)
        try:
            client = self._ensure_client()
            async with client.stream("POST", f"/ai/run/{model}", json=payload) as response:
                await self._raise_for_status(response, model=model)
                usage_meta: dict[str, Any] | None = None
                finished = False
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue  # SSE-Rahmen (Event-/Kommentarzeilen) überspringen
                    body = line[len("data:"):].strip()
                    if body == "[DONE]":
                        finished = True
                        break
                    try:
                        obj = json.loads(body)
                    except ValueError:
                        log.warning("Ungültige SSE-Zeile von Cloudflare ignoriert: %.120s", line)
                        continue
                    if obj.get("error"):
                        raise LLMResponseError(f"Cloudflare-Fehler: {obj['error']}")
                    if obj.get("usage"):
                        usage_meta = {"usage": obj["usage"]}
                    token = obj.get("response") or ""
                    if not token:
                        continue
                    visible = think_filter.feed(token)
                    if visible:
                        yield StreamChunk(content=visible)
                trailing = think_filter.flush()
                if trailing:
                    yield StreamChunk(content=trailing)
                yield StreamChunk(done=True, meta=usage_meta)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                "Zeitüberschreitung beim Streamen der Cloudflare-Antwort."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderConnectionError(
                f"Verbindung zur Cloudflare-API fehlgeschlagen: {exc.__class__.__name__}",
                provider=self.name,
            ) from exc

    async def chat(
        self,
        messages: list[ChatMessage],
        options: LLMOptions,
        *,
        model: str,
        keep_alive: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        self._require_credentials()
        del keep_alive  # Ollama-Konzept; in Workers AI ohne Funktion.
        payload = self._build_payload(messages, options, model=model, stream=False)
        try:
            response = await self._ensure_client().post(f"/ai/run/{model}", json=payload)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("Zeitüberschreitung bei der Cloudflare-Anfrage.") from exc
        except httpx.HTTPError as exc:
            raise ProviderConnectionError(
                f"Verbindung zur Cloudflare-API fehlgeschlagen: {exc.__class__.__name__}",
                provider=self.name,
            ) from exc
        await self._raise_for_status(response, model=model)
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMResponseError("Cloudflare lieferte keine gültige Chat-Antwort.") from exc
        result = data.get("result")
        if isinstance(result, dict):
            content = str(result.get("response", "") or "")
        else:
            content = str(result or "")
        if self._config.strip_think:
            content = strip_think_blocks(content)
        meta: dict[str, Any] = {}
        if isinstance(result, dict) and result.get("usage"):
            meta["usage"] = result["usage"]
        return content, meta

    # --- Hilfsfunktionen ------------------------------------------------------------
    async def _raise_for_status(self, response: httpx.Response, *, model: str = "") -> None:
        """Übersetzt Cloudflare-HTTP-Fehler in ZENJI-Fehlertypen (Nie-500-Garantie)."""
        if response.status_code < 400:
            return
        body = response.content if response.content else await response.aread()
        message = self._error_message(body)
        if response.status_code == 404 and model:
            raise ModelNotFoundError(
                f"Modell '{model}' ist bei Cloudflare Workers AI nicht vorhanden.",
                detail="Prüfe ZENJI_LLM__MODEL "
                "(z. B. '@cf/meta/llama-3.1-8b-instruct-fast'; Liste: GET /api/models).",
            )
        if response.status_code in (401, 403):
            raise ProviderConnectionError(
                f"Cloudflare hat den API-Token abgelehnt (HTTP {response.status_code}): {message}. "
                "Prüfe ZENJI_CLOUDFLARE_API_TOKEN (Berechtigung: Workers AI – Run).",
                provider=self.name,
            )
        if response.status_code == 429:
            raise LLMResponseError(
                f"Cloudflare-Rate-Limit erreicht (HTTP 429): {message} "
                "(Free-Plan: täglich 10.000 Neuronen)."
            )
        raise LLMResponseError(f"Cloudflare-Fehler (HTTP {response.status_code}): {message}")

    @staticmethod
    def _error_message(body: bytes | str) -> str:
        try:
            data = json.loads(body)
        except (ValueError, TypeError):
            return (body if isinstance(body, str) else body.decode("utf-8", "replace"))[:200]
        errors = data.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                return str(first.get("message", first))[:200]
            return str(first)[:200]
        return str(data.get("error", data))[:200]

    @staticmethod
    def _parse_model_entry(entry: dict[str, Any]) -> ModelInfo | None:
        """Filtert den Katalog auf Text-Generierungs-Modelle (chat-tauglich)."""
        name = entry.get("name", "")
        if not name:
            return None
        task_names: set[str] = set()
        task = entry.get("task")
        if isinstance(task, dict):
            task_names.add(str(task.get("name", "")).lower())
        for item in entry.get("tasks") or []:
            if isinstance(item, dict):
                task_names.add(str(item.get("name", "")).lower())
            else:
                task_names.add(str(item).lower())
        if task_names and not any(
            any(marker in entry_task for marker in _TEXT_TASK_MARKERS) for entry_task in task_names
        ):
            return None
        # "@cf/meta/llama-3.1-8b-instruct-fp8-fast" → family "meta", 8b, fp8
        parts = name.strip("@").split("/")
        family = parts[1] if len(parts) > 2 else None
        quantization_match = _QUANT_RE.search(name)
        parameter_match = _PARAM_RE.search(name)
        return ModelInfo(
            name=name,
            family=family,
            parameter_size=f"{parameter_match.group(1)}B" if parameter_match else None,
            quantization=quantization_match.group(1).lower() if quantization_match else None,
        )
