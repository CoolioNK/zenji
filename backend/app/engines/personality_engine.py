"""Personality Engine – ZENJIs konfigurierbare Identität.

Die Persönlichkeit lebt **ausschließlich** in der Datenbank (Seeding über
``backend/app/config/personalities.json``) – niemals fest im Python-Code.
Die Engine kompiliert aus den Profilfeldern einen konsistenten
Persönlichkeitskontext für das Sprachmodell.

Kompilierung ist deterministisch: dieselben Felder erzeugen denselben Text.
Numerische Eigenschaften (0–1) werden auf sprachliche Abstufungen abgebildet,
damit das Modell etwas Brauchbares erhält.
"""

from __future__ import annotations

import json
import re
from sqlalchemy.orm import Session

from app.core.exceptions import (
    PersonalityNameTakenError,
    PersonalityNotFoundError,
    PersonalityProtectedError,
)
from app.core.logging import get_logger
from app.database.models import PersonalityModel
from app.database.repositories.personalities import PersonalityRepository
from app.interfaces.base import ZenjiEngine

log = get_logger("personality_engine")

_LENGTH_DIRECTIVES = {
    "short": "Antworte knapp und auf den Punkt (in der Regel 2–4 Sätze).",
    "balanced": "Antworte ausführlich genug, aber ohne Ausschweifungen.",
    "detailed": "Antworte ausführlich und strukturiert, erkläre Zusammenhänge.",
}

_LEVELS = (
    (0.0, 0.2, "sehr gering"),
    (0.2, 0.4, "gering"),
    (0.4, 0.6, "mittel"),
    (0.6, 0.8, "stark"),
    (0.8, 1.01, "sehr stark"),
)

_FORMALITY_LEVELS = (
    (0.0, 0.2, "sehr locker/umgangssprachlich"),
    (0.2, 0.4, "locker"),
    (0.4, 0.6, "ausgewogen"),
    (0.6, 0.8, "formell orientiert"),
    (0.8, 1.01, "sehr formell"),
)

_LANGUAGE_DIRECTIVES = {
    "auto": "Antworte in der Sprache, in der der Nutzer schreibt.",
    "de": "Antworte immer auf Deutsch.",
    "en": "Antworte immer auf Englisch.",
}


def _level(value: float, levels: tuple[tuple[float, float, str], ...]) -> str:
    for low, high, label in levels:
        if low <= value < high:
            return label
    return "mittel"


def _json_text(value: object) -> str:
    """Normalisiert Situationsverhalten zu JSON-Text (dict oder str)."""
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value or "{}")


class PersonalityEngine(ZenjiEngine):
    """Verwaltet Profile und kompiliert den Persönlichkeitskontext."""

    name = "personality"

    def __init__(self) -> None:
        self._repo = PersonalityRepository()

    # --- Lifecycle -----------------------------------------------------------------
    async def start(self) -> None:
        log.info("PersonalityEngine bereit.")

    async def stop(self) -> None:
        return None

    # --- Lesen -----------------------------------------------------------------------
    def get(self, session: Session, personality_id: str) -> PersonalityModel:
        profile = self._repo.get(session, personality_id)
        if profile is None:
            raise PersonalityNotFoundError(f"Profil '{personality_id}' existiert nicht.")
        return profile

    def require_active(self, session: Session) -> PersonalityModel | None:
        """Aktives Profil oder None (fail-soft: Chat läuft auch ohne Profil)."""
        return self._repo.active(session)

    def list(self, session: Session) -> list[PersonalityModel]:
        return self._repo.list_all(session)

    # --- Schreiben ---------------------------------------------------------------------
    def create(self, session: Session, fields: dict) -> PersonalityModel:  # noqa: ANN401
        name = str(fields.get("name", "")).strip()
        if not name:
            from app.core.exceptions import ValidationError

            raise ValidationError("Profilname ist erforderlich.")
        if self._repo.get_by_name(session, name) is not None:
            raise PersonalityNameTakenError(f"Profil '{name}' existiert bereits.")
        profile = self._repo.create(
            session,
            name=name,
            identity=str(fields.get("identity", "")),
            base_personality=fields.get("base_personality", "custom"),
            communication_style=str(fields.get("communication_style", "")),
            formality=float(fields.get("formality", 0.5)),
            humor=float(fields.get("humor", 0.2)),
            directness=float(fields.get("directness", 0.6)),
            creativity=float(fields.get("creativity", 0.5)),
            response_length=fields.get("response_length", "balanced"),
            language=str(fields.get("language", "auto")),
            situational_behavior=_json_text(fields.get("situational_behavior", "{}")),
            is_system=False,
            is_active=False,
        )
        if fields.get("is_active"):
            self.activate(session, profile.id)
        return profile

    def update(self, session: Session, personality_id: str, fields: dict) -> PersonalityModel:  # noqa: ANN401
        profile = self.get(session, personality_id)
        allowed = {
            "name", "identity", "base_personality", "communication_style",
            "formality", "humor", "directness", "creativity", "response_length",
            "language", "situational_behavior", "is_active",
        }
        if "name" in fields:
            new_name = str(fields["name"]).strip()
            if not new_name:
                from app.core.exceptions import ValidationError

                raise ValidationError("Profilname darf nicht leer sein.")
            other = self._repo.get_by_name(session, new_name)
            if other is not None and other.id != profile.id:
                raise PersonalityNameTakenError(f"Profil '{new_name}' existiert bereits.")
        for key, value in fields.items():
            if key in allowed:
                if key == "situational_behavior":
                    value = _json_text(value)
                setattr(profile, key, value)
        session.flush()
        if fields.get("is_active"):
            self.activate(session, profile.id)
        return profile

    def activate(self, session: Session, personality_id: str) -> PersonalityModel:
        profile = self.get(session, personality_id)
        if not self._repo.activate(session, personality_id):
            raise PersonalityNotFoundError(f"Profil '{personality_id}' existiert nicht.")
        log.info("Persönlichkeit aktiviert: %s", profile.name)
        return profile

    def delete(self, session: Session, personality_id: str) -> None:
        profile = self.get(session, personality_id)
        if profile.is_system:
            raise PersonalityProtectedError(
                "Systemprofil kann nicht gelöscht werden – stattdessen ein eigenes Profil nutzen."
            )
        if profile.is_active:
            raise PersonalityProtectedError(
                "Aktives Profil kann nicht gelöscht werden – erst ein anderes Profil aktivieren."
            )
        self._repo.delete(session, personality_id)

    # --- Kompilierung ---------------------------------------------------------------------
    def compile_context(self, profile: PersonalityModel | None) -> str:
        """Erzeugt den Persönlichkeitsabschnitt für den Systemkontext.

        Ohne Profil liefert die Engine einen sicheren Minimalblock (fail-soft),
        damit der Chat auch vor dem ersten Seed funktioniert.
        """
        if profile is None:
            return (
                "## Persönlichkeit\n"
                "Kein Profil aktiv. Bleibe sachlich, klar und hilfsbereit.\n"
                "- Antworte in der Sprache des Nutzers.\n"
                "- Wenn du etwas nicht sicher weißt, sage es offen."
            )
        return self._render(profile)

    def _render(self, profile: PersonalityModel) -> str:
        behavior = profile.behavior_map()
        lines = [
            "## Persönlichkeit",
            f"Name: {profile.name}",
        ]
        if profile.identity:
            lines.append(f"Identität: {profile.identity.strip()}")
        lines.append(f"Grundhaltung: {profile.base_personality}")
        if profile.communication_style:
            lines.append(f"Kommunikationsstil: {profile.communication_style}")
        lines.append(f"Formalität: {_level(profile.formality, _FORMALITY_LEVELS)}")
        lines.append(f"Humor: {_level(profile.humor, _LEVELS)}")
        lines.append(f"Direktheit: {_level(profile.directness, _LEVELS)}")
        lines.append(f"Kreativität: {_level(profile.creativity, _LEVELS)}")
        lines.append(_LENGTH_DIRECTIVES.get(profile.response_length, _LENGTH_DIRECTIVES["balanced"]))
        if profile.language in _LANGUAGE_DIRECTIVES:
            lines.append(_LANGUAGE_DIRECTIVES[profile.language])
        if behavior:
            lines.append("Verhalten in besonderen Situationen:")
            for situation, conduct in behavior.items():
                lines.append(f"- Situation '{situation}': {conduct}")
        return "\n".join(lines)
