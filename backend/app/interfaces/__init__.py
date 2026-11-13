"""Erweiterungspunkte für zukünftige ZENJI-Engines.

Phase 1 implementiert diese Engines **nicht**.  Sie definiert jedoch stabile
Schnittstellen und dokumentiert, wie ZENJI Core sie später koordiniert:

- :class:`PolicyEngine`      – Verhaltensrichtlinien prüfen (Ein-/Ausgabe)
- :class:`MemoryEngine`      – Langzeitgedächtnis / relevante Kontexte
- :class:`WebEngine`         – Websuche und Website-Analyse
- :class:`ToolEngine`        – Tool Calling / Funktionsausführung
- :class:`PluginManager`     – dynamische Erweiterungen laden
- :class:`RAGEngine`         – Dokumentenanalyse & Retrieval
- :class:`ImageEngine`       – Bildverständnis / Bildgenerierung

Integration (Design, noch nicht aktiv):

- Engines werden über den :class:`~app.core.extensions.ExtensionRegistry`
  registriert.  ``ChatService`` fragt z. B. ``registry.get("policy")`` ab und
  nutzt die Engine nur, wenn sie registriert ist – in Phase 1 also nie.
  Dadurch bleibt der Chat-Pfad jetzt identisch und später erweiterbar,
  ohne Codepfade umbauen zu müssen.
"""

from __future__ import annotations

from app.interfaces.base import (
    ImageEngine,
    MemoryEngine,
    PluginManager,
    PolicyEngine,
    RAGEngine,
    ToolEngine,
    ToolSpec,
    WebEngine,
    ZenjiEngine,
)

__all__ = [
    "ImageEngine",
    "MemoryEngine",
    "PluginManager",
    "PolicyEngine",
    "RAGEngine",
    "ToolEngine",
    "ToolSpec",
    "WebEngine",
    "ZenjiEngine",
]
