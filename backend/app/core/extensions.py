"""ExtensionRegistry: Koordinationspunkt für zukünftige Engines.

Phase 2+ registriert Engines hier (z. B. ``registry.register(policy_engine)``).
Der ChatService und andere Komponenten holen Engines **optional** ab – fehlt
eine Engine, verläuft der Vorgang wie bisher (fail-soft).  So können Engines
separat entwickelt, getestet und aktiviert werden, ohne den Chat-Pfad zu
ändern.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.interfaces.base import ZenjiEngine

log = get_logger("extensions")


class ExtensionRegistry:
    """Namentlich sortierte Sammlung registrierter Engines."""

    def __init__(self) -> None:
        self._engines: dict[str, ZenjiEngine] = {}

    def register(self, engine: ZenjiEngine) -> None:
        """Registriert eine Engine (überschreibt keine fremde Registration –
        gleichnamige Engines werden ersetzt und der Vorgang geloggt)."""
        previous = self._engines.get(engine.name)
        self._engines[engine.name] = engine
        if previous is not None:
            log.warning("Engine '%s' ersetzt bereits registrierte Engine.", engine.name)

    def get(self, name: str) -> ZenjiEngine | None:
        """Engine abrufen oder None, wenn nicht registriert (fail-soft)."""
        return self._engines.get(name)

    def has(self, name: str) -> bool:
        return name in self._engines

    def names(self) -> list[str]:
        return sorted(self._engines)

    async def start_all(self) -> None:
        for engine in self._engines.values():
            await engine.start()
        if self._engines:
            log.info("Engines gestartet: %s", self.names())

    async def stop_all(self) -> None:
        for engine in reversed(list(self._engines.values())):
            try:
                await engine.stop()
            except Exception as exc:  # noqa: BLE001 – Herunterfahren darf nicht abbrechen
                log.warning("Engine '%s' konnte nicht sauber stoppen: %s", engine.name, exc)
        self._engines.clear()


registry_singleton = ExtensionRegistry()


def get_global_registry() -> ExtensionRegistry:
    """Standard-Registry der Anwendung (Phase 2 nutzt sie per Konvention)."""
    return registry_singleton


def as_payload(registry: ExtensionRegistry) -> dict[str, Any]:
    """Kompaktinfo für Health-Endpoint."""
    return {"registered": registry.names()}
