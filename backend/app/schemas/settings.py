"""Schemata für das Konfigurationssystem.

Unterscheidung:

- ``LLMSettings``          – allgemeine ZENJI-Parameter (modellunabhängig)
- ``OllamaProviderSettings`` – provider-spezifische Parameter (Ollama)
- ``PersonaSettings``      – Persönlichkeit / Verhaltensrichtlinien
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LLMSettings(BaseModel):
    """Allgemeine Sprachmodell-Parameter (alle zur Laufzeit änderbar)."""

    model_config = ConfigDict(protected_namespaces=())

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    temperature: float = Field(ge=0.0, le=2.0)
    top_p: float = Field(gt=0.0, le=1.0)
    top_k: int = Field(ge=1, le=200)
    repeat_penalty: float = Field(ge=0.5, le=2.0)
    num_predict: int = Field(ge=1, le=32768)
    num_ctx: int = Field(ge=512, le=131072)
    stream: bool = True


class OllamaProviderSettings(BaseModel):
    """Provider-spezifische Parameter für Ollama."""

    model_config = ConfigDict(protected_namespaces=())

    base_url: str = Field(pattern=r"^https?://")
    timeout: float = Field(ge=1.0, le=3600.0)
    connect_timeout: float = Field(ge=0.5, le=60.0)
    keep_alive: str = Field(min_length=1, max_length=20)
    think: bool | None = None
    strip_think: bool = True


class PersonaSettings(BaseModel):
    """Persönlichkeit und Verhaltensrichtlinien von ZENJI."""

    model_config = ConfigDict(protected_namespaces=())

    system_prompt: str = Field(min_length=1, max_length=8000)


class SettingsOut(BaseModel):
    """Effektive Einstellungen (Laufzeit-DB + Bootstrap-Defaults)."""

    model_config = ConfigDict(protected_namespaces=())

    llm: LLMSettings
    providers: ProvidersGroup
    persona: PersonaSettings


class ProvidersGroup(BaseModel):
    """Gruppierung provider-spezifischer Sektionen."""

    model_config = ConfigDict(protected_namespaces=())

    ollama: OllamaProviderSettings


class SettingsPatch(BaseModel):
    """Teilweise Änderung der Einstellungen (Deep-Merge je Gruppe)."""

    model_config = ConfigDict(protected_namespaces=())

    llm: LLMSettingsPartial | None = None
    providers: ProvidersPatch | None = None
    persona: PersonaSettingsPartial | None = None


class LLMSettingsPartial(BaseModel):
    """Teilweise änderbare allgemeine Parameter."""

    model_config = ConfigDict(protected_namespaces=(), extra="forbid")

    provider: str | None = Field(default=None, min_length=1)
    model: str | None = Field(default=None, min_length=1)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, gt=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=1, le=200)
    repeat_penalty: float | None = Field(default=None, ge=0.5, le=2.0)
    num_predict: int | None = Field(default=None, ge=1, le=32768)
    num_ctx: int | None = Field(default=None, ge=512, le=131072)
    stream: bool | None = None


class ProvidersPatch(BaseModel):
    """Teilweise änderbare Provider-Parameter."""

    model_config = ConfigDict(protected_namespaces=(), extra="forbid")

    ollama: OllamaProviderSettingsPartial | None = None


class OllamaProviderSettingsPartial(BaseModel):
    """Teilweise änderbare Ollama-Parameter."""

    model_config = ConfigDict(protected_namespaces=(), extra="forbid")

    base_url: str | None = Field(default=None, pattern=r"^https?://")
    timeout: float | None = Field(default=None, ge=1.0, le=3600.0)
    connect_timeout: float | None = Field(default=None, ge=0.5, le=60.0)
    keep_alive: str | None = Field(default=None, min_length=1, max_length=20)
    think: bool | None = None
    strip_think: bool | None = None


class PersonaSettingsPartial(BaseModel):
    """Teilweise änderbare Persönlichkeitsparameter."""

    model_config = ConfigDict(protected_namespaces=(), extra="forbid")

    system_prompt: str | None = Field(default=None, min_length=1, max_length=8000)
