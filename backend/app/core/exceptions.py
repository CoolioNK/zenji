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
    """Der Provider (z. B. Ollama oder Cloudflare) ist nicht erreichbar."""

    code = "OLLAMA_UNAVAILABLE"

    def __init__(self, message: str, *, provider: str = "ollama", detail: Any | None = None) -> None:
        super().__init__(message, detail=detail)
        self.provider = provider
        # Instance-attribut überschreibt den Klassen-Code: Der Fehlercode nennt
        # den tatsächlichen Provider (CLOUDFLARE_UNAVAILABLE statt OLLAMA_UNAVAILABLE).
        if provider and provider != "ollama":
            self.code = f"{provider.upper()}_UNAVAILABLE"


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


# --- Phase 2: Personality / Policy / Memory --------------------------------------


class PersonalityNotFoundError(ZenjiError):
    """Das angeforderte Persönlichkeitsprofil existiert nicht."""

    status_code = 404
    code = "PERSONALITY_NOT_FOUND"


class PersonalityProtectedError(ZenjiError):
    """Systemprofil oder aktives Profil darf nicht gelöscht werden."""

    status_code = 409
    code = "PERSONALITY_PROTECTED"


class PersonalityNameTakenError(ZenjiError):
    """Ein Profil mit diesem Namen existiert bereits."""

    status_code = 409
    code = "PERSONALITY_NAME_TAKEN"


class PolicyNotFoundError(ZenjiError):
    """Die angeforderte Regel existiert nicht."""

    status_code = 404
    code = "POLICY_NOT_FOUND"


class PolicyProtectedError(ZenjiError):
    """Systemregeln dürfen nicht über die API geändert/gelöscht werden."""

    status_code = 403
    code = "POLICY_SYSTEM_PROTECTED"


class PolicyIdTakenError(ZenjiError):
    """Eine Regel mit dieser ID existiert bereits."""

    status_code = 409
    code = "POLICY_ID_TAKEN"


class MemoryNotFoundError(ZenjiError):
    """Die angeforderte Erinnerung existiert nicht."""

    status_code = 404
    code = "MEMORY_NOT_FOUND"


# --- Phase 3: Web Intelligence ---------------------------------------------------


class WebIntelligenceError(ZenjiError):
    """Basis aller Web-Recherche-Fehler."""

    status_code = 502
    code = "WEB_INTELLIGENCE_ERROR"


class WebSecurityError(WebIntelligenceError):
    """Eine URL wurde vom SSRF-/Netzwerk-Schutz blockiert."""

    status_code = 403
    code = "WEB_SECURITY_BLOCKED"


class SearchProviderError(WebIntelligenceError):
    """Der Suchanbieter (SearXNG/Brave) ist nicht erreichbar oder antwortet
    fehlerhaft – verständliche Nutzermeldung statt Stacktrace."""

    status_code = 502
    code = "SEARCH_PROVIDER_UNAVAILABLE"


class WebFetchError(WebIntelligenceError):
    """Eine Website konnte nicht geladen werden (Netzwerk, Timeout, …)."""

    status_code = 502
    code = "WEB_FETCH_FAILED"


class ResearchNotFoundError(ZenjiError):
    """Die angeforderte Recherchesession existiert nicht."""

    status_code = 404
    code = "RESEARCH_NOT_FOUND"


class SourceNotFoundError(ZenjiError):
    """Die angeforderte Quelle existiert nicht."""

    status_code = 404
    code = "SOURCE_NOT_FOUND"
