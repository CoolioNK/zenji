"""Provider-Registry und -Fabrik.

Neue Anbieter werden hier registriert und in der Konfiguration über
``ZENJI_LLM_PROVIDER`` (bzw. ``llm.provider`` in der Laufzeitkonfiguration)
ausgewählt.  ZENJI enthält in Phase 1 genau einen Provider (Ollama); das
Registrierungsmuster ist für Phase 2+ (llama.cpp, OpenAI-kompatible APIs,
Image-Provider) vorbereitet.
"""

from __future__ import annotations

from typing import Callable, TypeAlias

from app.core.exceptions import ConfigurationError
from app.engines.providers.base import LLMProvider
from app.engines.providers.ollama import OllamaProvider

ProviderFactory: TypeAlias = Callable[[str, dict], LLMProvider]

_REGISTRY: dict[str, Callable[[dict], LLMProvider]] = {}


def register_provider(name: str, factory: Callable[[dict], LLMProvider]) -> None:
    """Registriert einen Provider-Typ (Name → Fabrik(config_dict))."""
    _REGISTRY[name.lower()] = factory


def create_provider(name: str, config: dict) -> LLMProvider:
    """Erstellt einen Provider anhand seines Namens."""
    key = (name or "").lower().strip()
    factory = _REGISTRY.get(key)
    if factory is None:
        raise ConfigurationError(
            f"Unbekannter LLM-Provider '{name}'.",
            detail={"verfügbar": sorted(_REGISTRY)},
        )
    return factory(config)


def available_providers() -> list[str]:
    return sorted(_REGISTRY)


def _default_registry() -> None:
    from app.core.config import OllamaDefaults

    def ollama_factory(config: dict) -> OllamaProvider:
        return OllamaProvider(
            base_url=config.get("base_url", "http://localhost:11434"),
            config=OllamaDefaults(**{k: v for k, v in config.items() if k != "base_url"}),
        )

    register_provider(OllamaProvider.name, ollama_factory)


_default_registry()
