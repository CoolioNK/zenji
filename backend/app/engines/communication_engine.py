"""Communication Engine – situative Kommunikationsmodi von ZENJI (v0.3.0).

ZENJI passt seinen Ton der Situation an. Fünf Modi stehen bereit:

- **Casual** (Standard): locker, freundlich, humorvoll.
- **Roast**: frech, sarkastisch, provokant – Grenzen bleiben gewahrt.
- **Fokus**: konzentriert, präzise, lösungsorientiert.
- **Empathie**: ruhig, warm, verständnisvoll.
- **Open Talk**: offen zu persönlichen, intimen und kontroversen Themen
  (immer im Rahmen von Alter, Einverständnis und Sicherheit).

Arbeitsweise (deterministisch, fail-soft, modellunabhängig):

- Die Modi leben **ausschließlich** in ``backend/app/config/
  communication_modes.json`` – niemals fest im Python-Code.
- ``detect_mode`` wählt: 1. explizite Nutzeranfrage („Roast-Modus“), 2.
  Gefühls-Signale (Empathie), 3. Themen-Signale (Open Talk), 4. Aufgabensignale
  (Fokus), sonst der Default (Casual).  Ein manueller Override des Nutzers
  schlägt immer die automatische Erkennung.
- ``mode_directives`` übersetzt den Modus in einen Kontextabschnitt
  („## Kommunikationsmodus“), den die Context Engine direkt hinter der
  Persönlichkeit einfügt.  Der Abschnitt markiert den Modus ausdrücklich als
  **temporär** – ein Modus ist keine Persönlichkeitsänderung.

Kein Zustand, keine Datenbank: Modi sind bewusst flüchtig (pro Nachricht
entschieden) und überleben Neustarts nicht als „Stimmung“.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.core.logging import get_logger
from app.interfaces.base import ZenjiEngine

log = get_logger("communication_engine")

#: Seed-Datei mit den Modi-Definitionen (kein Python-Hardcoding von Modi).
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
MODES_FILE = CONFIG_DIR / "communication_modes.json"

#: Stabile Modus-Keys (API-Kontrakt für ``ChatRequest.mode``).
COMMUNICATION_MODE_KEYS = ("casual", "roast", "focus", "empathy", "open_talk")

#: Fallback, falls die Seed-Datei fehlt oder beschädigt ist.
DEFAULT_MODE = "casual"

#: Abschnitts-Kopf im kompilierten Kontext.
_MODE_HEADER = "## Kommunikationsmodus"

_TEMPORARY_NOTE = (
    "temporärer Modus für diese Unterhaltung – die zugrundeliegende "
    "Persönlichkeit bleibt unverändert"
)


@dataclass(slots=True)
class CommunicationMode:
    """Ein Modus aus der Seed-Datei."""

    key: str
    label: str
    directive: str
    explicit: tuple[str, ...] = ()
    signals: tuple[str, ...] = ()


class CommunicationManager(ZenjiEngine):
    """Erkennt den situativen Modus und kompiliert seine Stilvorgaben."""

    name = "communication"

    def __init__(self, config_path: Path | None = None) -> None:
        self._path = config_path or MODES_FILE
        self._modes: dict[str, CommunicationMode] = {}
        self._default = DEFAULT_MODE
        self._priority: tuple[str, ...] = ()
        self._load()

    # --- Lifecycle -----------------------------------------------------------------
    async def start(self) -> None:
        log.info(
            "CommunicationManager bereit (%d Modi, Standard '%s').",
            len(self._modes), self._default,
        )

    async def stop(self) -> None:
        return None

    # --- Laden -----------------------------------------------------------------------
    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning(
                "Modi-Datei '%s' nicht lesbar (%s) – Standardmodus ohne Direktive.",
                self._path, exc,
            )
            return
        modes: dict[str, CommunicationMode] = {}
        for entry in data.get("modes", []):
            if not isinstance(entry, dict):
                continue
            key = str(entry.get("key", "")).strip()
            if not key:
                continue
            modes[key] = CommunicationMode(
                key=key,
                label=str(entry.get("label", key)),
                directive=str(entry.get("directive", "")).strip(),
                explicit=tuple(str(p).lower() for p in entry.get("explicit", []) or []),
                signals=tuple(str(p).lower() for p in entry.get("signals", []) or []),
            )
        if not modes:
            log.warning("Keine Modi in '%s' – Standardmodus ohne Direktive.", self._path)
            return
        default = str(data.get("default", DEFAULT_MODE)).strip().lower()
        priority = tuple(
            key for key in (str(k).strip().lower() for k in data.get("priority", []) or [])
            if key in modes
        )
        self._modes = modes
        self._default = default if default in modes else DEFAULT_MODE
        self._priority = priority or tuple(self._modes)

    # --- Moduswahl ---------------------------------------------------------------------
    def detect_mode(self, text: str, *, override: str | None = None) -> str:
        """Wählt den Modus für eine Nachricht.

        Reihenfolge: manueller Override → explizite Modusanfrage →
        Signal-Priorität (siehe Seed-Datei) → Standardmodus.
        """
        if override:
            normalized = override.strip().lower()
            if normalized in self._modes:
                return normalized
            log.warning(
                "Unbekannter Kommunikationsmodus '%s' – automatische Erkennung.", override
            )

        lowered = (text or "").strip().lower()
        if lowered:
            # 1. Explizite Modusanfrage schlägt alles.
            for mode in self._modes.values():
                if any(pattern in lowered for pattern in mode.explicit):
                    return mode.key
            # 2. Signale in definierter Priorität (Gefühle vor Themen vor Aufgaben).
            for key in self._priority:
                mode = self._modes.get(key)
                if mode is not None and any(p in lowered for p in mode.signals):
                    return mode.key
        return self._default

    # --- Kompilierung ---------------------------------------------------------------------
    def mode_directives(self, mode_key: str) -> str:
        """Kontextabschnitt für einen Modus (leer, wenn Modus/Direktive fehlt)."""
        mode = self._modes.get(mode_key)
        if mode is None or not mode.directive:
            return ""
        return (
            f"{_MODE_HEADER}\n"
            f"Aktuell: {mode.label} ({_TEMPORARY_NOTE}).\n"
            f"{mode.directive}"
        )
    # --- Auskunft (für Status-API) -------------------------------------------------------------
    def available(self) -> list[dict[str, str]]:
        """Alle Modi als [{key, label}] (Reihenfolge der Seed-Datei)."""
        return [{"key": mode.key, "label": mode.label} for mode in self._modes.values()]

    @property
    def default_mode(self) -> str:
        """Standardmodus (Fail-soft: ``casual``)."""
        return self._default


__all__ = [
    "COMMUNICATION_MODE_KEYS",
    "CommunicationManager",
    "CommunicationMode",
    "DEFAULT_MODE",
]
