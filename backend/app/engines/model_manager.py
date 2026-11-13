"""Modellverwaltung: Verfügbarkeit, Informationen, klare Fehlermeldungen."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.exceptions import ModelNotFoundError, ProviderConnectionError
from app.core.logging import get_logger
from app.engines.providers.base import LLMProvider, ModelInfo, ProviderStatus

log = get_logger("model_manager")


@dataclass(slots=True)
class ModelStatus:
    """Zusammengefasster Status für UI und Health-Endpoint."""

    model: str
    provider_available: bool
    model_available: bool
    message: str


class ModelManager:
    """Prüft Modellverfügbarkeit beim aktiven Provider und übersetzt Fehler."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def provider_status(self) -> ProviderStatus:
        return await self._provider.status()

    async def list_models(self) -> list[ModelInfo]:
        return await self._provider.list_models()

    async def info(self, model: str) -> ModelInfo:
        return await self._provider.model_info(model)

    async def is_available(self, model: str) -> bool:
        return await self._provider.has_model(model)

    async def ensure_available(self, model: str) -> None:
        """Wirft verständliche Fehler, wenn Provider oder Modell fehlen."""
        status = await self._provider.status()
        if not status.available:
            provider_name = self._provider.name
            raise ProviderConnectionError(
                f"{provider_name.capitalize()} ist nicht erreichbar "
                f"({status.detail or 'unbekannter Grund'}). "
                "Bitte den Modellserver starten und erneut versuchen."
            )
        if not await self._provider.has_model(model):
            raise ModelNotFoundError(
                f"Modell '{model}' ist nicht verfügbar.",
                detail=(
                    f"Das Modell muss zuerst geladen werden. Für Ollama: "
                    f"'ollama pull {model}' ausführen – die Gewichte liegen "
                    "dann auf der externen SSD (siehe docs/STORAGE.md)."
                ),
            )
        log.debug("Modell '%s' ist verfügbar", model)

    async def status_for(self, model: str) -> ModelStatus:
        """Nicht werfender Status (für Health-Endpoint)."""
        provider_status = await self._provider.status()
        if not provider_status.available:
            return ModelStatus(
                model=model,
                provider_available=False,
                model_available=False,
                message=f"Provider nicht erreichbar: {provider_status.detail or ''}".strip(),
            )
        try:
            available = await self._provider.has_model(model)
        except ProviderConnectionError:
            return ModelStatus(
                model=model,
                provider_available=False,
                model_available=False,
                message="Verbindung zum Provider während der Prüfung verloren.",
            )
        message = f"Modell '{model}' verfügbar." if available else (
            f"Modell '{model}' nicht geladen. "
            f"Laden via 'ollama pull {model}' (Gewichte auf der SSD, siehe docs/STORAGE.md)."
        )
        return ModelStatus(
            model=model,
            provider_available=True,
            model_available=available,
            message=message,
        )
