"""Ausnahmen-Hierarchie von ZENJI.

Jede fachliche Ausnahme trägt einen stabilen ``code`` und einen HTTP-Status.
Die API-Route wandelt sie in ein einheitliches JSON-Fehlerformat um:

    {"error": {"code": "...", "message": "...", "detail": {...}}}
"""

from __future__ import annotations

from typing import Any


class ZenjiError(Exception):
    """Basisausnahme aller fachlichen ZENJI-Fehler."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, *, detail: Any | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class ConfigurationError(ZenjiError):
    """Ungültige oder unvollständige Konfiguration."""

    status_code = 500
    code = "CONFIGURATION_ERROR"


class StorageError(ZenjiError):
    """Basis aller Speicherpfad-Probleme."""

    status_code = 503
    code = "STORAGE_UNAVAILABLE"


class StorageUnavailableError(StorageError):
    """Die externe SSD fehlt, ist getrennt oder nicht beschreibbar."""

    code = "STORAGE_UNAVAILABLE"


class DatabaseError(ZenjiError):
    """Fehler beim Zugriff auf die SQLite-Datenbank."""

    status_code = 503
    code = "DATABASE_ERROR"


class LLMError(ZenjiError):
    """Basis aller Sprachmodell-Fehler."""

    status_code = 502
    code = "LLM_ERROR"


class ProviderConnectionError(LLMError):
    """Der Provider (z. B. Ollama) ist nicht erreichbar."""

    code = "OLLAMA_UNAVAILABLE"

    def __init__(self, message: str, *, provider: str = "ollama", detail: Any | None = None) -> None:
        super().__init__(message, detail=detail)
        self.provider = provider


class ModelNotFoundError(LLMError):
    """Das konfigurierte Modell ist beim Provider nicht vorhanden."""

    status_code = 409
    code = "MODEL_NOT_FOUND"


class LLMTimeoutError(LLMError):
    """Das Sprachmodell hat nicht rechtzeitig geantwortet."""

    status_code = 504
    code = "LLM_TIMEOUT"


class LLMResponseError(LLMError):
    """Der Provider hat eine ungültige oder fehlerhafte Antwort geliefert."""

    code = "LLM_RESPONSE_ERROR"


class ConversationNotFoundError(ZenjiError):
    """Die angeforderte Konversation existiert nicht."""

    status_code = 404
    code = "CONVERSATION_NOT_FOUND"


class ValidationError(ZenjiError):
    """Fachliche Validierungsprobleme (z. B. ungültige Einstellungswerte)."""

    status_code = 422
    code = "VALIDATION_ERROR"
