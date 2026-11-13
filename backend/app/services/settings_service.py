"""Settings-Service: effektive Konfiguration = DB (Laufzeit) ∪ Bootstrap (.env).

Die Bootstrap-Konfiguration (:class:`app.core.config.Settings`) liefert die
Startwerte; über ``PATCH /api/settings`` geänderte Werte werden in der
SQLite-Tabelle ``settings`` als JSON gespeichert und überschreiben die
Defaults.  Zurücksetzen = DB-Eintrag löschen (Platzhalter für Phase 2).

Unterscheidung allgemeine vs. provider-spezifische Parameter:

- Gruppe ``llm``       → allgemeine ZENJI-Parameter
- Gruppe ``providers`` → provider-spezifische Parameter (``ollama``)
- Gruppe ``persona``   → Persönlichkeit / Verhaltensrichtlinien
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import get_logger
from app.database.repositories.settings import SettingsRepository
from app.engines.providers.base import LLMOptions
from app.schemas.settings import (
    LLMSettings,
    LLMSettingsPartial,
    OllamaProviderSettings,
    OllamaProviderSettingsPartial,
    PersonaSettings,
    PersonaSettingsPartial,
    ProvidersGroup,
    SettingsOut,
    SettingsPatch,
)

log = get_logger("settings_service")

_KEYS = {"llm": "llm", "providers": "providers", "persona": "persona"}


class SettingsService:
    """Liest, validiert und speichert Laufzeit-Einstellungen."""

    def __init__(self, bootstrap: Settings) -> None:
        self._bootstrap = bootstrap
        self._repo = SettingsRepository()

    # --- Defaults --------------------------------------------------------------
    def defaults(self) -> SettingsOut:
        """Bootstrap-Werte als SettingsOut-Struktur."""
        bs = self._bootstrap
        return SettingsOut(
            llm=LLMSettings(
                provider=bs.llm.provider,
                model=bs.llm.model,
                temperature=bs.llm.temperature,
                top_p=bs.llm.top_p,
                top_k=bs.llm.top_k,
                repeat_penalty=bs.llm.repeat_penalty,
                num_predict=bs.llm.num_predict,
                num_ctx=bs.llm.num_ctx,
                stream=bs.llm.stream,
            ),
            providers=ProvidersGroup(
                ollama=OllamaProviderSettings(
                    base_url=bs.ollama_base_url,
                    timeout=bs.ollama.timeout,
                    connect_timeout=bs.ollama.connect_timeout,
                    keep_alive=bs.ollama.keep_alive,
                    think=bs.ollama.think,
                    strip_think=bs.ollama.strip_think,
                )
            ),
            persona=PersonaSettings(system_prompt=bs.persona_system_prompt),
        )

    # --- Lesen ------------------------------------------------------------------
    def effective(self, session: Session) -> SettingsOut:
        """Effektive Einstellungen: Defaults + gespeicherte Änderungen."""
        merged = self._merge_over_defaults()
        stored = {key: self._repo.get(session, key) for key in _KEYS.values()}
        return self._apply_stored(merged, stored)

    def _merge_over_defaults(self) -> dict[str, dict[str, Any]]:
        base = self.defaults().model_dump()
        return base

    def _apply_stored(
        self, merged: dict[str, dict[str, Any]], stored: dict[str, str | None]
    ) -> SettingsOut:
        for key, raw in stored.items():
            if not raw:
                continue
            try:
                payload: dict[str, Any] = json.loads(raw)
            except ValueError:
                log.warning("Ungültige gespeicherte Einstellung '%s' ignoriert.", key)
                continue
            if key == "llm":
                clean = LLMSettingsPartial(**payload).model_dump(exclude_none=True)
                merged["llm"].update(clean)
            elif key == "providers":
                ollama_patch = payload.get("ollama") or {}
                clean = OllamaProviderSettingsPartial(**ollama_patch).model_dump(exclude_none=True)
                merged["providers"]["ollama"].update(clean)
            elif key == "persona":
                clean = PersonaSettingsPartial(**payload).model_dump(exclude_none=True)
                merged["persona"].update(clean)
        return SettingsOut.model_validate(merged)

    # --- Schreiben ---------------------------------------------------------------
    def patch(self, session: Session, patch: SettingsPatch) -> SettingsOut:
        """Validiert und speichert Änderungen (Deep-Merge je Gruppe)."""
        if patch.llm is not None:
            self._save_group(session, "llm", patch.llm.model_dump(exclude_none=True))
        if patch.providers is not None and patch.providers.ollama is not None:
            self._save_group(
                session,
                "providers",
                {"ollama": patch.providers.ollama.model_dump(exclude_none=True)},
            )
        if patch.persona is not None:
            self._save_group(session, "persona", patch.persona.model_dump(exclude_none=True))
        return self.effective(session)

    def _save_group(self, session: Session, key: str, payload: dict[str, Any]) -> None:
        existing = self._repo.get(session, key)
        stored: dict[str, Any] = json.loads(existing) if existing else {}
        if key == "providers":
            incoming_ollama = payload.get("ollama", {})
            stored.setdefault("ollama", {}).update(incoming_ollama)
        else:
            stored.update(payload)
        self._repo.set(session, key, json.dumps(stored, ensure_ascii=False))
        log.info("Einstellungen gespeichert: %s", key)

    def reset(self, session: Session) -> SettingsOut:
        """Alle Laufzeit-Änderungen verwerfen (zurück zu Bootstrap-Defaults)."""
        for key in _KEYS.values():
            self._repo.set(session, key, "{}")
        return self.effective(session)

    # --- Chat-Integration ------------------------------------------------------------
    def llm_options(self, settings: SettingsOut) -> LLMOptions:
        """Baut die providerunabhängigen Optionen für einen LLM-Aufruf."""
        llm = settings.llm
        return LLMOptions(
            temperature=llm.temperature,
            top_p=llm.top_p,
            top_k=llm.top_k,
            repeat_penalty=llm.repeat_penalty,
            num_predict=llm.num_predict,
            num_ctx=llm.num_ctx,
        )

    def active_model(self, settings: SettingsOut) -> str:
        return settings.llm.model

    def keep_alive(self, settings: SettingsOut) -> str | None:
        return settings.providers.ollama.keep_alive
