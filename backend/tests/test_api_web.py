"""Tests: Web Intelligence API (Phase 3) – /api/web, /api/research, /api/sources.

Alle Tests laufen offline: Der Suchanbieter wird per FakeSearchProvider
gemockt (über ``app.state.web_intelligence``), Webabrufe per MockTransport
in der Research Engine (Monkeypatch ``_research_engine``).
"""

from __future__ import annotations

import httpx
import pytest

from app.database.repositories.web import WebRepository
from app.services.web_intelligence_service import WebConfig
from app.web_intelligence.browser_engine import BrowserEngine
from app.web_intelligence.research_engine import ResearchEngine
from app.web_intelligence.search_engine import SearchEngine
from tests.conftest import FakeSearchProvider
from tests.test_research_engine import PAGE_A, _result


def _install_fake_research(app, provider: FakeSearchProvider) -> list[str]:
    """Monkeypatch: web.research nutzt Fake-Provider + Mock-Webabrufe."""
    calls: list[str] = []

    def fake_engine():
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(404, text="")
            return httpx.Response(
                200, text=PAGE_A, headers={"content-type": "text/html"}
            )

        browser = BrowserEngine(
            transport=httpx.MockTransport(handler),
            per_host_delay=0.0,
            resolver=lambda host: ("93.184.216.34",),
        )
        return ResearchEngine(
            db=app.state.database,
            search_engine=SearchEngine({provider.name: provider}),
            browser=browser,
        )

    original = app.state.web_intelligence._research_engine

    def patched():
        calls.append("engine")
        return fake_engine()

    app.state.web_intelligence._research_engine = patched  # type: ignore[method-assign]
    return calls


# --- /api/web -------------------------------------------------------------------------


async def test_web_settings_keinen_api_key_zurueck(client):
    http, app = client
    response = await http.get("/api/web/settings")
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "searxng"
    assert data["searxng_url"] == "http://localhost:8888"
    assert "brave_api_key" not in data
    assert data["brave_api_key_set"] is False


async def test_web_settings_patchen_und_validieren(client):
    http, app = client
    response = await http.patch(
        "/api/web/settings",
        json={"provider": "brave", "searxng_url": "http://localhost:9999/", "cache_ttl_s": 1800},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "brave"
    assert data["searxng_url"] == "http://localhost:9999"
    assert data["cache_ttl_s"] == 1800.0

    # Unbekannter Provider → 422:
    bad = await http.patch("/api/web/settings", json={"provider": "google"})
    assert bad.status_code == 422

    # Persistenz: zweites Lesen zeigt den geänderten Stand:
    again = await http.get("/api/web/settings")
    assert again.json()["provider"] == "brave"


async def test_web_status_ist_ehrlich(client):
    http, app = client
    response = await http.get("/api/web/status")
    assert response.status_code == 200
    data = response.json()
    # SearXNG läuft in der Testumgebung nicht → ehrlich "nicht verfügbar":
    assert data["provider"] == "searxng"
    assert data["search"]["available"] is False
    assert data["browser"]["httpx"]["available"] is True
    assert "nicht installiert" in data["browser"]["playwright"]["detail"]
    assert data["planner_modes"] == ["quick", "standard", "deep"]


async def test_web_suche_mit_fake_provider(client):
    http, app = client
    provider = FakeSearchProvider(
        [_result("https://a.example/x", "Titel", "a.example")]
    )
    app.state.web_intelligence._search_engine = (  # type: ignore[method-assign]
        lambda config: SearchEngine({provider.name: provider})
    )
    response = await http.post("/api/web/search", json={"query": "python version"})
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "python version"
    assert len(data["results"]) == 1
    assert data["results"][0]["url"] == "https://a.example/x"
    assert data["results"][0]["provider"] == "searxng"

    # Unbekannter Provider in Anfrage → 422:
    bad = await http.post("/api/web/search", json={"query": "x", "provider": "bing"})
    assert bad.status_code == 422


async def test_web_cache_loeschen(client):
    http, app = client
    response = await http.delete("/api/web/cache")
    assert response.status_code == 200
    assert response.json() == {"deleted": 0}  # leerer Cache in Testumgebung


# --- /api/research ---------------------------------------------------------------------


async def test_research_post_liefert_report_und_persistiert(client):
    http, app = client
    provider = FakeSearchProvider([_result("https://a.example/py", "Python", "a.example")])
    _install_fake_research(app, provider)
    response = await http.post(
        "/api/research", json={"question": "Was ist die neueste Python-Version?", "mode": "quick"}
    )
    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "done"
    assert report["session_id"]
    assert report["sources"][0]["marker"] == 1

    # Historie + Detail:
    listing = await http.get("/api/research")
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    detail = await http.get(f"/api/research/{report['session_id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "done"
    assert body["report"]["question"]
    assert body["queries"][0]["query"]
    assert len(body["citations"]) == len(report["facts"])

    delete = await http.delete(f"/api/research/{report['session_id']}")
    assert delete.status_code == 200
    gone = await http.get(f"/api/research/{report['session_id']}")
    assert gone.status_code == 404
    assert gone.json()["error"]["code"] == "RESEARCH_NOT_FOUND"


async def test_research_stream_liefert_sse_ereigniskette(client):
    http, app = client
    provider = FakeSearchProvider([_result("https://a.example/py", "Python", "a.example")])
    _install_fake_research(app, provider)
    async with http.stream(
        "POST", "/api/research/stream",
        json={"question": "Was ist die neueste Python-Version?", "mode": "quick"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        raw = b""
        async for chunk in response.aiter_bytes():
            raw += chunk
    from tests.conftest import parse_sse

    events = parse_sse(raw)
    names = [name for name, _ in events]
    assert names[0] == "start"
    assert "research" in names
    assert names[-1] == "done"
    research_events = [data for name, data in events if name == "research"]
    steps = [event["step"] for event in research_events]
    assert steps[0] == "planned"  # ehrliche Kette ab Plan
    assert "searching" in steps and "fetching" in steps
    done_data = events[-1][1]
    assert done_data["report"]["status"] == "done"


async def test_research_stream_mit_provider_ausfall(client):
    http, app = client
    provider = FakeSearchProvider(error="Suchanbieter ist nicht erreichbar.")
    _install_fake_research(app, provider)
    async with http.stream(
        "POST", "/api/research/stream", json={"question": "Was gibt es Neues bei Python?", "mode": "quick"}
    ) as response:
        raw = b""
        async for chunk in response.aiter_bytes():
            raw += chunk
    from tests.conftest import parse_sse

    events = parse_sse(raw)
    names = [name for name, _ in events]
    assert "error" in names or events[-1][0] == "done"
    failed = [data for name, data in events if name == "research" and data["step"] == "search_failed"]
    assert failed, "Suchfehler muss als ehrliches research-Event kommen"
    assert "nicht erreichbar" in failed[0]["detail"]


# --- /api/sources -----------------------------------------------------------------------


async def test_quellen_liste_und_loeschung(client):
    http, app = client
    provider = FakeSearchProvider([_result("https://a.example/py", "Python", "a.example")])
    _install_fake_research(app, provider)
    await http.post(
        "/api/research", json={"question": "Was ist die neueste Python-Version?", "mode": "quick"}
    )

    listing = await http.get("/api/sources")
    assert listing.status_code == 200
    data = listing.json()
    assert data["total"] >= 1
    source = data["sources"][0]
    assert source["domain"] == "a.example"
    assert source["source_type"] in ("offiziell", "unbekannt")

    detail = await http.get(f"/api/sources/{source['id']}")
    assert detail.status_code == 200
    snapshot = await http.get(f"/api/sources/{source['id']}/snapshot")
    assert snapshot.status_code == 200
    assert snapshot.json()["char_count"] > 0

    delete = await http.delete(f"/api/sources/{source['id']}")
    assert delete.status_code == 200
    missing = await http.get(f"/api/sources/{source['id']}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "SOURCE_NOT_FOUND"


async def test_quellen_filter_und_validierung(client):
    http, app = client
    response = await http.get("/api/sources", params={"type": "falsch"})
    assert response.status_code == 422
    empty = await http.get("/api/sources", params={"domain": "niemand.example"})
    assert empty.status_code == 200
    assert empty.json()["total"] == 0


# --- Chat-Integration ---------------------------------------------------------------------


async def test_chat_auto_ohne_recherche_bedarf_laeuft_ohne_web(client, monkeypatch):
    http, app = client
    events_seen: list[dict] = []

    class _Core(app.state.zenji_core.__class__):
        pass

    # Konzeptfrage → Bedarfserkennung greift nicht → keine research-Events:
    async with http.stream(
        "POST", "/api/chat/stream",
        json={"message": "Erkläre kurz, wie ein Transformer funktioniert."},
    ) as response:
        raw = b""
        async for chunk in response.aiter_bytes():
            raw += chunk
    from tests.conftest import parse_sse

    events = parse_sse(raw)
    names = [name for name, _ in events]
    assert "research" not in names
    assert names[0] == "start" and names[-1] == "done"


async def test_chat_mit_erzwungener_recherche_und_zitat_validierung(client, monkeypatch):
    http, app = client
    provider = FakeSearchProvider([_result("https://a.example/py", "Python", "a.example")])
    _install_fake_research(app, provider)

    # Antwort des Fake-Modells enthält erfundenen [5]-Marker → muss entfernt werden:
    llm_provider = app.state.llm_engine._provider
    llm_provider.reply = "Python 3.14 ist aktuell [1]. Ohne Beleg erfunden [5]."

    async with http.stream(
        "POST", "/api/chat/stream",
        json={"message": "Was ist die neueste Python-Version?", "research": "quick"},
    ) as response:
        raw = b""
        async for chunk in response.aiter_bytes():
            raw += chunk
    from tests.conftest import parse_sse

    events = parse_sse(raw)
    names = [name for name, _ in events]
    assert names[0] == "start"
    assert "research" in names  # echte Recherche-Events im Chatstream
    done = [data for name, data in events if name == "done"][0]
    assert done["research"]["status"] == "done"
    assert done["research"]["citations_corrected"] == 1  # [5] entfernt
    assert "[5]" not in done["content"]
    assert "[1]" in done["content"]


async def test_chat_research_off_unterdrueckt_recherche(client, monkeypatch):
    http, app = client
    provider = FakeSearchProvider([_result("https://a.example/py", "Python", "a.example")])
    install = _install_fake_research(app, provider)

    async with http.stream(
        "POST", "/api/chat/stream",
        json={"message": "Was ist die neueste Python-Version?", "research": "off"},
    ) as response:
        raw = b""
        async for chunk in response.aiter_bytes():
            raw += chunk
    from tests.conftest import parse_sse

    events = parse_sse(raw)
    names = [name for name, _ in events]
    assert "research" not in names
    assert install == []  # Recherche-Engine nie angefordert


async def test_context_preview_recherchiert_nicht_live(client):
    http, app = client
    provider = FakeSearchProvider([_result("https://a.example/py", "Python", "a.example")])
    install = _install_fake_research(app, provider)
    response = await http.get(
        "/api/core/context-preview",
        params={"message": "Was ist die neueste Python-Version?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["research_planned"] is True  # Bedarf erkannt …
    assert install == []  # … aber Preview recherchiert nicht live
    assert all(section["key"] != "research" or not section["included"] for section in data["sections"])
