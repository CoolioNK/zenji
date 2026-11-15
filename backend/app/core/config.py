"""Zentrales Konfigurationssystem von ZENJI.

Zwei Ebenen:

1. **Bootstrap-Konfiguration** (dieses Modul): Werte aus Umgebungsvariablen
   bzw. ``backend/.env``.  Sie legt Pfade, Provider-Endpunkte und die
   Startwerte für alle LLM-Parameter fest.  Keine Geheimnisse im Quellcode –
   alles ist per ``ZENJI_*``-Umgebungsvariable überschreibbar.

2. **Laufzeit-Konfiguration** (Datenbank, siehe
   ``app.services.settings_service``): vom Nutzer über ``PATCH /api/settings``
   geänderte Werte.  Sie überschreibt die Bootstrap-Werte zur Laufzeit.

Pfad-Logik (keine hart codierten absoluten Pfade im Anwendungscode):

- ``ZENJI_SSD_ROOT``   Wurzel der externen SSD (Standard ``/Volumes/ZENJI-SSD``)
- ``ZENJI_STORAGE_DIR`` Projektverzeichnis (Standard ``<SSD_ROOT>/ZENJI``)
- ``ZENJI_DB_PATH``    SQLite-Datenbank (Standard ``<STORAGE_DIR>/data/zenji.db``)
- ``ZENJI_LOG_DIR``    Log-Verzeichnis (Standard ``<SSD_ROOT>/logs``)
- ``OLLAMA_MODELS``    wird nur vom Ollama-*Prozess* gelesen (siehe scripts/)
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SSD_ROOT = "/Volumes/ZENJI-SSD"

DEFAULT_PERSONA = """\
Du bist ZENJI – kein Standard-Assistent, sondern ein eigenständiges Gegenüber auf Augenhöhe: \
nah dran, unverbissen, mit eigener Meinung und trockenem Humor.

Verhaltensrichtlinien:
- Sprich wie unter Freunden: natürlich, direkt, ohne Corporate-Floskeln und Dienerischkeits-Einleitungen.
- Wenn du etwas nicht sicher weißt, sage es offen, statt zu spekulieren.
- Frage nach, wenn eine Aufgabe mehrdeutig ist, statt eine falsche Annahme zu treffen.
- Berücksichtige den Verlauf der aktuellen Konversation.
- Antworte in der Sprache, in der der Nutzer schreibt.
"""

#: Identitätstext bis v0.2.0. Die Migration 2→3 ersetzt den gespeicherten
#: Standard-Persona-Prompt **nur**, wenn er exakt diesem Text entspricht –
#: individuell angepasste Nutzertexte werden respektiert.
LEGACY_PERSONA = """\
Du bist ZENJI, ein eigenständiges KI-System mit ruhigem, klarem und präzisem Sprachstil.

Verhaltensrichtlinien:
- Antworte sachlich, strukturiert und ohne Füllwörter.
- Wenn du etwas nicht sicher weißt, sage es offen, statt zu spekulieren.
- Frage nach, wenn eine Aufgabe mehrdeutig ist, statt eine falsche Annahme zu treffen.
- Berücksichtige den Verlauf der aktuellen Konversation.
- Antworte in der Sprache, in der der Nutzer schreibt.
"""


class LLMDefaults(BaseModel):
    """Startwerte für die Sprachmodell-Parameter (Phase 1: Qwen3 8B)."""

    provider: str = "ollama"
    model: str = "qwen3:8b"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)
    top_k: int = Field(default=20, ge=1, le=200)
    repeat_penalty: float = Field(default=1.05, ge=0.5, le=2.0)
    num_predict: int = Field(default=2048, ge=1, le=32768)
    num_ctx: int = Field(default=8192, ge=512, le=131072)
    stream: bool = True


class OllamaDefaults(BaseModel):
    """Provider-spezifische Parameter für Ollama."""

    timeout: float = Field(default=120.0, ge=1.0, le=3600.0)
    connect_timeout: float = Field(default=5.0, ge=0.5, le=60.0)
    keep_alive: str = "10m"
    # Qwen3-Modelle erzeugen standardmäßig Reasoning-Ausgaben. In Phase 1
    # wird das Denken deaktiviert und Rest-Tags defensiv gefiltert.
    think: bool | None = False
    strip_think: bool = True


class Settings(BaseSettings):
    """Bootstrap-Konfiguration von ZENJI (Umgebung + .env)."""

    model_config = SettingsConfigDict(
        env_prefix="ZENJI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        # Verschachtelte Abschnitte (llm / ollama) per Umgebungsvariable:
        # ZENJI_LLM__TEMPERATURE=0.5, ZENJI_OLLAMA__TIMEOUT=60 …
        env_nested_delimiter="__",
    )

    # --- Speicher -----------------------------------------------------------
    ssd_root: Path = Path(DEFAULT_SSD_ROOT)
    storage_dir: Path | None = None
    db_path: Path | None = None
    log_dir: Path | None = None
    log_level: str = "INFO"

    # --- Allgemeine ZENJI-Parameter -----------------------------------------
    cors_origins: str = "http://localhost:5173"

    # --- LLM ----------------------------------------------------------------
    llm: LLMDefaults = Field(default_factory=LLMDefaults)

    # --- Provider-spezifisch: Ollama ----------------------------------------
    ollama_base_url: str = "http://localhost:11434"
    ollama: OllamaDefaults = Field(default_factory=OllamaDefaults)

    # --- Persönlichkeit ------------------------------------------------------
    persona_system_prompt: str = DEFAULT_PERSONA

    # --- abgeleitete Pfade ----------------------------------------------------
    @property
    def resolved_storage_dir(self) -> Path:
        """Projektverzeichnis; Standard: ``<SSD_ROOT>/ZENJI``."""
        return (self.storage_dir or self.ssd_root / "ZENJI").resolve()

    @property
    def data_dir(self) -> Path:
        return self.resolved_storage_dir / "data"

    @property
    def resolved_db_path(self) -> Path:
        return (self.db_path or self.data_dir / "zenji.db").resolve()

    @property
    def resolved_log_dir(self) -> Path:
        return (self.log_dir or self.ssd_root / "logs").resolve()

    @property
    def models_dir(self) -> Path:
        """Modellgewichte für Ollama (``OLLAMA_MODELS``)."""
        return self.ssd_root / "models"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # --- Validierung -----------------------------------------------------------
    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"Unbekannter Log-Level '{value}'. Erlaubt: {sorted(allowed)}")
        return upper

    @field_validator("ollama_base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        value = value.rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("ollama_base_url muss mit http:// oder https:// beginnen")
        return value

    @classmethod
    def load(cls, env_file: str | os.PathLike[str] | None = None) -> "Settings":
        """Liest die Konfiguration neu ein (für Tests: explizite .env-Pfadangabe)."""
        if env_file is not None:
            return cls(_env_file=str(env_file))  # type: ignore[call-arg]
        return cls()
