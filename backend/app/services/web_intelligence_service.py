"""Web Intelligence Service (Phase 3) – Fassade der Recherche-Schicht.

Verbindet die ``app/web_intelligence``-Module mit Datenbank und
Laufzeit-Einstellungen:

- **Einstellungen** (Tabelle ``settings``, Schlüssel ``web_intelligence``):
  Suchanbieter, SearXNG-Adresse, Brave-API-Key, Sprache, Cache-TTL.  Der
  SearXNG-Endpunkt ist – wie der Ollama-Endpunkt – eine bewusste
  Nutzereinstellung und **kein** SSRF-geschützter Webabruf; trotzdem ist
  nur http(s) erlaubt und die Antwortgröße begrenzt.
- **Search** (``POST /api/web/search``): eine Anfrage, normalisierte Treffer.
- **Research** (``POST /api/research[/stream]``): kompletter Durchlauf mit
  echten Progress-Meldungen und kontrollierbarem Abbruch.
- **Sources / History / Cache**: Verwaltungszugriffe für das Control Center.
- **Chat-Integration** (``ZenjiCore``): Bedarfserkennung, Recherche-Ausführung,
  Kontext-Datenblock und Antwort-Zitat-Validierung.

Der Service baut die SearchEngine **pro Aufruf** aus den aktuellen
Einstellungen (Konfiguration änderbar ohne Neustart); die BrowserEngine
bleibt persistent (robots.txt-Cache, Höflichkeits-Abstände, Statistik).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.database.database import Database
from app.database.models import SettingModel
from app.database.repositories.web import DEFAULT_CACHE_TTL_S, WebRepository
from app.web_intelligence.browser_engine import BrowserEngine
from app.web_intelligence.citation_engine import CitationEngine, SourceRef
from app.web_intelligence.content_extractor import ContentExtractor
from app.web_intelligence.research_cache import ResearchCache
from app.web_intelligence.research_engine import MAX_CONTEXT_CHARS, ResearchEngine, context_block
from app.web_intelligence.research_planner import RESEARCH_MODES, ResearchPlanner, normalize_mode
from app.web_intelligence.search_engine import (
    BraveProvider,
    SearchEngine,
    SearchProvider,
    SearXNGProvider,
)
from app.web_intelligence.source_analysis import SourceAnalysisEngine
from app.web_intelligence.source_manager import SourceManager

if TYPE_CHECKING:  # pragma: no cover
    pass

log = get_logger("web_intelligence")

WEB_SETTINGS_KEY = "web_intelligence"
PROVIDERS = ("searxng", "brave")


@dataclass(slots=True)
class WebConfig:
    """Laufzeit-Konfiguration der Web Intelligence (Nutzereinstellungen)."""

    provider: str = "searxng"
    searxng_url: str = "http://localhost:8888"
    brave_api_key: str = ""
    language: str = "de"
    cache_ttl_s: float = DEFAULT_CACHE_TTL_S

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class WebIntelligenceService:
    """Fassade: Suche, Recherche, Quellen, Cache, Status, Chat-Hooks."""

    name = "web_intelligence"

    def __init__(self, database: Database) -> None:
        self._db = database
        self._repo = WebRepository()
        self._planner = ResearchPlanner()
        # Persistente BrowserEngine (robots-Cache, Höflichkeit, Statistik):
        self._browser = BrowserEngine()
        self._extractor = ContentExtractor()
        self._citations = CitationEngine()
        self._analysis = SourceAnalysisEngine()

    # --- Konfiguration ---------------------------------------------------------------------

    def get_config(self) -> WebConfig:
        """Effektive Web-Konfiguration (DB überschreibt Defaults)."""
        config = WebConfig()
        try:
            with self._db.session() as session:
                record = session.get(SettingModel, WEB_SETTINGS_KEY)
            if record is not None:
                try:
                    stored = json.loads(record.value or "{}")
                except ValueError:
                    stored = {}
                if isinstance(stored, dict):
                    for key in ("provider", "searxng_url", "brave_api_key", "language"):
                        value = stored.get(key)
                        if isinstance(value, str) and value:
                            setattr(config, key, value)
                    ttl = stored.get("cache_ttl_s")
                    if isinstance(ttl, (int, float)) and ttl > 0:
                        config.cache_ttl_s = float(ttl)
        except Exception as exc:  # noqa: BLE001 – ohne SSD arbeiten wir mit Defaults
            log.debug("Web-Einstellungen nicht lesbar (Defaults aktiv): %s", exc)
        return config

    def patch_config(self, fields: dict[str, Any]) -> WebConfig:
        """Nutzereinstellungen ändern (validiert, ohne SSID-Abhängigkeit)."""
        config = self.get_config()
        provider = fields.get("provider")
        if provider is not None:
            if str(provider) not in PROVIDERS:
                raise ValidationError(
                    f"Unbekannter Suchanbieter '{provider}'. Erlaubt: {PROVIDERS}."
                )
            config.provider = str(provider)
        searxng = fields.get("searxng_url")
        if searxng is not None:
            if not str(searxng).startswith(("http://", "https://")):
                raise ValidationError(
                    "SearXNG-Adresse muss mit http:// oder https:// beginnen."
                )
            config.searxng_url = str(searxng).rstrip("/")
        if fields.get("brave_api_key") is not None:
            config.brave_api_key = str(fields["brave_api_key"])
        if fields.get("language") is not None:
            config.language = str(fields["language"])
        ttl = fields.get("cache_ttl_s")
        if ttl is not None:
            try:
                config.cache_ttl_s = float(ttl)
            except (TypeError, ValueError) as exc:
                raise ValidationError("cache_ttl_s muss eine Zahl sein.") from exc
            if not 60.0 <= config.cache_ttl_s <= 86_400.0:
                raise ValidationError("cache_ttl_s muss zwischen 60 und 86400 Sekunden liegen.")
        try:
            with self._db.session() as session:
                record = session.get(SettingModel, WEB_SETTINGS_KEY)
                payload = json.dumps(config.as_dict(), ensure_ascii=False)
                if record is None:
                    session.add(SettingModel(key=WEB_SETTINGS_KEY, value=payload))
                else:
                    record.value = payload
        except ValidationError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("Web-Einstellungen konnten nicht gespeichert werden: %s", exc)
        return config

    # --- Suchen -----------------------------------------------------------------------------

    def _search_engine(self, config: WebConfig) -> SearchEngine:
        providers: dict[str, SearchProvider] = {
            "searxng": SearXNGProvider(config.searxng_url, language=config.language),
            "brave": BraveProvider(config.brave_api_key),
        }
        return SearchEngine(providers, default_provider=config.provider)

    async def search(
        self, query: str, *, provider: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Eine Suchanfrage (``POST /api/web/search``)."""
        engine = self._search_engine(self.get_config())
        results = await engine.search(query, provider=provider, limit=limit)
        return [result.as_dict() for result in results]

    # --- Recherche ------------------------------------------------------------------------------

    def needs_research(self, text: str) -> bool:
        """Deterministische Bedarfserkennung (Planner-Heuristik)."""
        return self._planner.needs_research(text)

    def _research_engine(self) -> ResearchEngine:
        config = self.get_config()
        return ResearchEngine(
            db=self._db,
            search_engine=self._search_engine(config),
            browser=self._browser,
            extractor=self._extractor,
            source_manager=SourceManager(self._repo),
            analysis=self._analysis,
            citations=self._citations,
            cache=ResearchCache(self._repo, ttl_s=config.cache_ttl_s),
            repository=self._repo,
        )

    async def research(
        self,
        question: str,
        *,
        mode: str | None = None,
        progress: Any = None,
        abort_event: Any = None,
    ) -> dict[str, Any]:
        """Vollständige Recherche (Report-Dict, Session persistiert)."""
        engine = self._research_engine()
        return await engine.run(
            question, mode=mode, force=True, progress=progress, abort_event=abort_event
        )

    @staticmethod
    def context_block(report: dict[str, Any], *, max_chars: int = MAX_CONTEXT_CHARS) -> str:
        """Recherche-Report als Datenblock-Inhalt für die Context Engine."""
        return context_block(report, max_chars=max_chars)

    @staticmethod
    def validate_answer(text: str, report: dict[str, Any]) -> tuple[str, list[str]]:
        """Citation-Validierung der Antwort (erfundene Marker entfernt)."""
        refs = [
            SourceRef(
                source_id=str(ref.get("source_id", "")),
                title=str(ref.get("title", "")),
                url=str(ref.get("url", "")),
                domain=str(ref.get("domain", "")),
                source_type=str(ref.get("source_type", "unbekannt")),
            )
            for ref in (report.get("refs") or [])
        ]
        result = CitationEngine().validate(text, refs)
        return result.cleaned_text, list(result.warnings)

    # --- Status -----------------------------------------------------------------------------------

    async def status(self) -> dict[str, Any]:
        """Ehrliche Betriebszustände (Control Center „Browser Status“)."""
        config = self.get_config()
        try:
            search_status = await self._search_engine(config).provider(config.provider).status()
        except ValidationError as exc:
            search_status = {"available": False, "detail": exc.message}
        try:
            storage = self.storage_stats()
            cache_stats = self.cache_stats()
        except Exception as exc:  # noqa: BLE001 – Status degradiert sauber
            storage = {"available": False, "detail": str(exc)}
            cache_stats = {"total": 0}
        return {
            "provider": config.provider,
            "search": search_status,
            "browser": self._browser.status(),
            "cache": cache_stats,
            "storage": storage,
            "planner_modes": list(RESEARCH_MODES),
            "version": "0.5.0",
        }

    def cache_stats(self) -> dict[str, Any]:
        with self._db.session() as session:
            stats = self._repo.cache_stats(session)
        stats["ttl_s"] = self.get_config().cache_ttl_s
        return stats

    def storage_stats(self) -> dict[str, int]:
        with self._db.session() as session:
            return self._repo.storage_stats(session)

    def clear_cache(self) -> int:
        """Benutzeraktion: gesamten Research Cache löschen."""
        with self._db.session() as session:
            return self._repo.clear_cache(session)

    def purge_cache(self) -> int:
        with self._db.session() as session:
            return self._repo.purge_expired_cache(session)

    # --- Quellen & History (Verwaltungszugriffe) ------------------------------------------------------

    def list_sources(
        self, session: Session, *, domain: str | None = None,
        source_type: str | None = None, limit: int = 200,
    ):
        return self._repo.list_sources(
            session, domain=domain, source_type=source_type, limit=limit
        )

    def get_source(self, session: Session, source_id: str):
        return self._repo.get_source(session, source_id)

    def delete_source(self, session: Session, source_id: str) -> bool:
        return self._repo.delete_source(session, source_id)

    def snapshot(self, session: Session, source_id: str):
        return self._repo.get_snapshot(session, source_id)

    def list_sessions(self, session: Session, *, limit: int = 50):
        return self._repo.list_sessions(session, limit=limit)

    def get_session(self, session: Session, research_id: str):
        return self._repo.get_session(session, research_id)

    def delete_session(self, session: Session, research_id: str) -> bool:
        return self._repo.delete_session(session, research_id)

    def queries(self, session: Session, research_id: str):
        return self._repo.queries_of_session(session, research_id)

    def citations(self, session: Session, research_id: str):
        return self._repo.citations_of_session(session, research_id)


__all__ = ["PROVIDERS", "WebConfig", "WebIntelligenceService", "normalize_mode", "RESEARCH_MODES"]
