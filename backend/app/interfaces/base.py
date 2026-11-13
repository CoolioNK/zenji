"""Abstrakte Basisklassen der zukünftigen ZENJI-Engines (Phase 2+).

Alle Engines folgen demselben Grundmuster (ZenjiEngine):

- asynchron
- registriert sich unter einem stabilen Namen im ExtensionRegistry
- fail-soft: Fehler werden als fachliche Ausnahmen gemeldet, nie als Crash

Jede Klasse dokumentiert ihren geplanten Platz im Datenfluss.  Die Methoden
sind Absichtserklärungen der Schnittstelle (nur ``check``/``collect``-
Signaturen), damit Phase 2 ohne Breaking Changes anschließen kann.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any


class ZenjiEngine(ABC):
    """Basisprotokoll jeder ZENJI-Engine."""

    #: Registrierungsname im ExtensionRegistry, z. B. "policy", "memory".
    name: str

    @abstractmethod
    async def start(self) -> None:
        """Ressourcen bereitstellen (wird beim App-Start aufgerufen)."""

    @abstractmethod
    async def stop(self) -> None:
        """Ressourcen freigeben (wird beim Herunterfahren aufgerufen)."""


class PolicyEngine(ZenjiEngine):
    """Prüft Nutzer- und Modelltexte gegen Verhaltensrichtlinien.

    Geplanter Datenfluss: ChatService ruft vor dem Senden
    ``check_incoming`` und vor dem Speichern/Streaming ``check_outgoing``.
    Verstöße werden als PolicyViolation gemeldet; Phase 1 hat keine Policy
    (Voreinstellung: alles erlaubt).
    """

    name = "policy"

    @abstractmethod
    async def check_incoming(self, text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Nutzeranfrage prüfen. Rückgabe: {"allowed": bool, "reason": str|None}."""

    @abstractmethod
    async def check_outgoing(self, text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Modellantwort prüfen, bevor sie ausgeliefert/gespeichert wird."""


class MemoryEngine(ZenjiEngine):
    """Langzeitgedächtnis über Konversationsgrenzen hinweg.

    Geplanter Datenfluss: ChatService baut das Kontextfenster heute aus dem
    Konversationsverlauf (SQLite).  Später ergänzt ``collect_context``
    relevante Erinnerungen (Fakten, Präferenzen) als zusätzliche
    System-/Kontextnachrichten.
    """

    name = "memory"

    @abstractmethod
    def collect_context(
        self, conversation_id: str, user_message: str, limit: int = 5
    ) -> AsyncIterator[str]:
        """Relevante Erinnerungen zum aktuellen Thema liefern."""


class WebEngine(ZenjiEngine):
    """Websuche und Website-Analyse.

    Geplanter Datenfluss: wird über die ToolEngine als Tool exponiert
    (``web_search``, ``analyze_page``); Antworten enthalten Quellenangaben.
    """

    name = "web"

    @abstractmethod
    async def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Suchergebnisse: [{"title", "url", "snippet"}]."""

    @abstractmethod
    async def analyze_page(self, url: str) -> dict[str, Any]:
        """Seiteninhalt extrahieren und zusammenfassen."""


@dataclass(slots=True)
class ToolSpec:
    """Beschreibung eines Tools für das zukünftige Tool Calling."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


class ToolEngine(ZenjiEngine):
    """Funktionsausführung: LLM fordert Tools an, Engine führt sie aus."""

    name = "tool"

    @abstractmethod
    def tools(self) -> Sequence[ToolSpec]:
        """Verfügbare Tools deklarieren (für den LLM-Prompt)."""

    @abstractmethod
    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Tool ausführen; Ergebnis geht zurück ins Modell."""


class PluginManager(ZenjiEngine):
    """Lädt externe Erweiterungen (Pakete/Verzeichnisse) dynamisch."""

    name = "plugin"

    @abstractmethod
    async def discover(self) -> list[dict[str, Any]]:
        """Verfügbare Plugins auflisten."""

    @abstractmethod
    async def load(self, plugin_id: str) -> dict[str, Any]:
        """Plugin aktivieren (registriert Engines/Tools/Provider)."""


class RAGEngine(ZenjiEngine):
    """Dokumentenanalyse & Retrieval-Augmented Generation."""

    name = "rag"

    @abstractmethod
    async def ingest(self, document: bytes, filename: str) -> dict[str, Any]:
        """Dokument indexieren; Rückgabe: {"document_id", "chunks"}."""

    @abstractmethod
    def retrieve(self, query: str, top_k: int = 5) -> AsyncIterator[str]:
        """Relevante Ausschnitte für eine Frage liefern."""


class ImageEngine(ZenjiEngine):
    """Bildverständnis und (später) Bildgenerierung."""

    name = "image"

    @abstractmethod
    async def describe(self, image: bytes, question: str | None = None) -> str:
        """Bildinhalt analysieren und antworten."""

    @abstractmethod
    async def generate(self, prompt: str, **kwargs: Any) -> bytes:
        """Bild aus Prompt erzeugen (Phase 3+)."""
