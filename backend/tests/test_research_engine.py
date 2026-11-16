"""Tests: Research Engine (Phase 3) – Offline-End-to-End mit Mock-Web."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.core.exceptions import SearchProviderError
from app.database.database import Database
from app.database.models import (
    CitationModel,
    ResearchSessionModel,
    SourceModel,
    SearchQueryModel,
)
from app.database.repositories.web import WebRepository
from app.web_intelligence.browser_engine import BrowserEngine
from app.web_intelligence.citation_engine import CitationEngine
from app.web_intelligence.content_extractor import ContentExtractor
from app.web_intelligence.research_cache import ResearchCache
from app.web_intelligence.research_engine import ResearchEngine, context_block
from app.web_intelligence.search_engine import SearchEngine
from app.web_intelligence.source_analysis import SourceAnalysisEngine
from app.web_intelligence.source_manager import SourceManager
from tests.conftest import FakeSearchProvider

PAGE_A = """<html><head><title>Python 3.14 ist da</title></head><body>
<article><p>Die neueste Version von Python ist 3.14 und wurde im Oktober 2026
veröffentlicht. Die Release Notes nennen neue Syntaxfeatures und
Geschwindigkeitsverbesserungen für die Interpreter-Schleife.</p></article>
</body></html>"""

PAGE_B = """<html><head><title>KI-Modelle auf dem Mac</title></head><body>
<article><p>Modell X benötigt 16 GB RAM. Das Modell läuft auf den meisten
Mac-Systemen stabil und ist für lokale Aufgaben ausreichend schnell.</p></article>
</body></html>"""

PAGE_C = """<html><head><title>KI-Modelle im Test</title></head><body>
<article><p>Modell X benötigt 12 GB RAM. Die Redaktion hat das Modell mehrere
Wochen auf verschiedenen Rechnern getestet und Werte dokumentiert.</p></article>
</body></html>"""


def _result(url: str, title: str, domain: str, snippet: str = "Kurzer Text"):
    return {"url": url, "title": title, "content": snippet, "domain": domain}


def _db(tmp_path: Path) -> Database:
    settings = Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]
    db = Database(settings)
    db.create_schema()
    return db


def _make_engine(db: Database, provider: FakeSearchProvider, pages: dict[str, str]):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404, text="")
        body = pages.get(str(request.url))
        if body is None:
            return httpx.Response(404, text="nf")
        return httpx.Response(200, text=body, headers={"content-type": "text/html"})

    browser = BrowserEngine(
        transport=httpx.MockTransport(handler),
        per_host_delay=0.0,
        resolver=lambda host: ("93.184.216.34",),
    )
    search = SearchEngine({provider.name: provider})
    return ResearchEngine(
        db=db,
        search_engine=search,
        browser=browser,
        extractor=ContentExtractor(),
        source_manager=SourceManager(),
        analysis=SourceAnalysisEngine(),
        citations=CitationEngine(),
        cache=ResearchCache(),
        repository=WebRepository(),
    )


# --- Happy Path (quick) ----------------------------------------------------------------------


async def test_quick_recherche_ende_zu_ende(tmp_path):
    provider = FakeSearchProvider(
        [
            _result("https://a.example/python", "Python 3.14", "a.example"),
            _result("https://b.example/python", "Release Notes", "b.example"),
            _result("https://c.example/python", "Download", "c.example"),
            _result("https://d.example/python", "Extra", "d.example"),
            _result("https://e.example/python", "Noch eins", "e.example"),
        ]
    )
    pages = {
        "https://a.example/python": PAGE_A,
        "https://b.example/python": PAGE_A,
        "https://c.example/python": PAGE_A,
        "https://d.example/python": PAGE_A,
        "https://e.example/python": PAGE_A,
    }
    engine = _make_engine(_db(tmp_path), provider, pages)
    events: list[dict] = []
    report = await engine.run(
        "Was ist die neueste Version von Python?", mode="quick",
        progress=events.append,
    )

    # Report-Struktur:
    assert report["status"] == "done"
    assert report["mode"] == "quick"
    assert report["session_id"], "Session-ID muss im Report stehen"
    assert len(report["queries"]) == 1  # quick: genau eine Anfrage
    assert len(report["sources"]) == 3  # Moduslimit quick
    assert report["facts"], "Fakten mit Belegen erwartet"
    for fact in report["facts"]:
        assert 1 <= fact["marker"] <= len(report["sources"])
    assert report["sources"][0]["marker"] == 1

    # Ehrliche Progress-Kette (nur echte Schritte):
    steps = [event["step"] for event in events]
    assert steps[0] == "planned"
    assert "searching" in steps and "searched" in steps
    assert "fetching" in steps and "fetched" in steps
    assert steps[-1] == "done"

    # Persistenz:
    db: Database = engine._db
    with db.session() as session:
        sessions = list(session.scalars(select(ResearchSessionModel)))
        assert len(sessions) == 1
        assert sessions[0].status == "done"
        assert sessions[0].source_count == 3
        assert sessions[0].duration_ms is not None
        queries = list(session.scalars(select(SearchQueryModel)))
        assert len(queries) == 1 and queries[0].result_count == 3
        sources = list(session.scalars(select(SourceModel)))
        assert len(sources) == 3
        citations = list(session.scalars(select(CitationModel)))
        assert len(citations) == len(report["facts"])


async def test_context_block_hat_marker_und_regeln(tmp_path):
    provider = FakeSearchProvider([_result("https://a.example/x", "Titel", "a.example")])
    engine = _make_engine(_db(tmp_path), provider, {"https://a.example/x": PAGE_A})
    report = await engine.run("Was ist die neueste Version von Python?", mode="quick")
    block = context_block(report)
    assert "RECHERCHE-FRAGE" in block
    assert "[1] " in block
    assert "QUELLEN (mit Marker)" in block
    assert "ERMITTELTE FAKTEN" in block
    assert "[1]" in block
    # Wrapper übernimmt die Context Engine:
    assert "[INHALT_BEGINN]" not in block
    assert "ANTWORTREGELN" in block


# --- Widersprüche -------------------------------------------------------------------------------


async def test_widerspruch_zwischen_zwei_quellen_wird_erkannt(tmp_path):
    provider = FakeSearchProvider(
        [
            _result("https://a.example/model", "Test A", "a.example"),
            _result("https://b.example/model", "Test B", "b.example"),
        ]
    )
    pages = {"https://a.example/model": PAGE_B, "https://b.example/model": PAGE_C}
    engine = _make_engine(_db(tmp_path), provider, pages)
    report = await engine.run(
        "Vergleiche die aktuell besten KI-Modelle für meinen Mac.", mode="standard"
    )

    assert len(report["sources"]) == 2
    assert report["contradictions"], "16-GB/12-GB-Widerspruch erwartet"
    statements = report["contradictions"][0]["statements"]
    numbers = {tuple(statement["numbers"]) for statement in statements}
    assert numbers == {(16.0,), (12.0,)}
    assert any(s["marker"] == 1 for s in statements) and any(s["marker"] == 2 for s in statements)


# --- Fehlerfälle --------------------------------------------------------------------------------


async def test_provider_ausfall_liefert_status_failed_mit_verstaendlicher_meldung(tmp_path):
    provider = FakeSearchProvider(error="Suchanbieter SearXNG ist nicht erreichbar unter http://localhost:8888.")
    engine = _make_engine(_db(tmp_path), provider, {})
    report = await engine.run("Was ist die neueste Version von Python?", mode="quick")
    assert report["status"] == "failed"
    assert "nicht erreichbar" in report["stats"]["error"]

    with engine._db.session() as session:
        sessions = list(session.scalars(select(ResearchSessionModel)))
        assert sessions[0].status == "failed"


async def test_ssrf_blockierte_url_wird_nicht_gelesen_und_dokumentiert(tmp_path):
    provider = FakeSearchProvider(
        [_result("http://192.168.5.5/intern", "Intern", "192.168.5.5")]
    )
    engine = _make_engine(_db(tmp_path), provider, {})
    report = await engine.run("Was ist die neueste Version von Python?", mode="quick")
    assert report["status"] == "partial"
    assert report["facts"] == []
    assert any("nicht lesbar" in note or "Website(s)" in note for note in report["notes"])

    with engine._db.session() as session:
        sources = list(session.scalars(select(SourceModel)))
        assert len(sources) == 1
        assert sources[0].status == "blocked"


async def test_leere_anfrage_endet_failed(tmp_path):
    engine = _make_engine(_db(tmp_path), FakeSearchProvider([]), {})
    report = await engine.run("   ")
    assert report["status"] == "failed"


async def test_abbruch_wird_kontrolliert_durchgefuehrt(tmp_path):
    provider = FakeSearchProvider([_result("https://a.example/x", "T", "a.example")])
    engine = _make_engine(_db(tmp_path), provider, {"https://a.example/x": PAGE_A})
    abort = asyncio.Event()
    abort.set()
    report = await engine.run("Was ist die neueste Version von Python?", mode="quick", abort_event=abort)
    assert report["status"] == "cancelled"


# --- Cache --------------------------------------------------------------------------------------


async def test_zweiter_lauf_benutzt_cache_ohne_neue_suche(tmp_path):
    provider = FakeSearchProvider([_result("https://a.example/x", "Titel", "a.example")])
    pages = {"https://a.example/x": PAGE_A}
    db = _db(tmp_path)
    engine = _make_engine(db, provider, pages)

    first = await engine.run("Was ist die neueste Version von Python?", mode="quick")
    assert first["status"] == "done"
    assert provider.calls  # Live-Suche lief

    provider2 = FakeSearchProvider([])  # zweiter Provider: würde fehlschlagen, wenn genutzt
    engine2 = _make_engine(db, provider2, pages)
    second = await engine2.run("Was ist die neueste Version von Python?", mode="quick")
    assert provider2.calls == []  # Such-Cache getroffen
    assert second["status"] == "done"
    assert second["stats"]["cache_hits"] >= 1
    assert second["facts"], "Fakten aus Cache-Inhalt erwartet"


# --- Limits ------------------------------------------------------------------------------------


async def test_domain_diversitaet_bei_auswahl(tmp_path):
    results = [_result(f"https://d{i}.example/x", f"T{i}", f"d{i}.example") for i in range(6)]
    provider = FakeSearchProvider(results)
    pages = {f"https://d{i}.example/x": PAGE_A for i in range(6)}
    engine = _make_engine(_db(tmp_path), provider, pages)
    report = await engine.run("Was ist die neueste Version von Python?", mode="quick")
    assert len(report["sources"]) == 3  # Limit quick
    domains = [source["domain"] for source in report["sources"]]
    assert len(set(domains)) == 3  # Diversität: keine Wiederholung nötig


async def test_relevanz_und_klassifikation_im_report(tmp_path):
    provider = FakeSearchProvider([_result("https://a.example/docs/index", "Docs", "a.example")])
    engine = _make_engine(_db(tmp_path), provider, {"https://a.example/docs/index": PAGE_A})
    report = await engine.run("Was ist die neueste Version von Python?", mode="quick")
    source = report["sources"][0]
    # /docs-Pfad → offizielle Dokumentationsquelle:
    assert source["source_type"] == "offiziell"
    assert "type_reason" in source and source["type_reason"]
    assert 0.0 <= source["relevance"] <= 1.0
