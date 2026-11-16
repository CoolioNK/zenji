"""Tests: Browser Engine (Phase 3) – Hops, robots.txt, Limits, Status.

Alle Tests laufen ohne echten Netzwerkzugriff: HTTP wird per
``httpx.MockTransport`` simuliert, DNS per injiziertem Resolver.
"""

from __future__ import annotations

import time

import httpx
import pytest

from app.core.exceptions import WebFetchError, WebSecurityError
from app.web_intelligence.browser_engine import BrowserEngine
from app.web_intelligence import ssrf

HTML_PAGE = """<html><head><title>ZENJI Testseite</title>
<link rel="canonical" href="https://example.com/kanonisch">
<meta name="description" content="Testbeschreibung">
<meta name="author" content="Max Mustermann">
<meta property="og:title" content="OG Titel">
</head><body><p>Inhalt</p></body></html>"""


def _resolver(*addresses: str):
    def _resolve(hostname: str) -> tuple[str, ...]:
        return tuple(addresses) or ("93.184.216.34",)

    return _resolve


def _make_handler(
    pages: dict[str, httpx.Response],
    *,
    robots: dict[str, str] | None = None,
):
    """MockTransport-Handler mit robots.txt-Routing und Abrufprotokoll."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if request.url.path == "/robots.txt":
            # Achtung: httpx 0.28 liefert ``netloc`` als bytes → ``host`` nutzen.
            origin = f"{request.url.scheme}://{request.url.host}"
            content = (robots or {}).get(origin)
            if content is None:
                return httpx.Response(404, text="")
            return httpx.Response(200, text=content)
        response = pages.get(url)
        if response is None:
            return httpx.Response(404, text="nicht gefunden")
        return response

    handler.calls = calls  # type: ignore[attr-defined]
    return handler


def _make_engine(pages, *, robots=None, resolver=None, **kwargs) -> BrowserEngine:
    handler = _make_handler(pages, robots=robots)
    defaults = dict(
        transport=httpx.MockTransport(handler),
        per_host_delay=0.0,
        resolver=resolver or _resolver("93.184.216.34"),
    )
    defaults.update(kwargs)
    engine = BrowserEngine(**defaults)
    engine._handler = handler  # type: ignore[attr-defined]  # Test-Zugriff
    return engine


def _page(body: str, *, status: int = 200, content_type: str = "text/html", headers=None):
    return httpx.Response(
        status, text=body, headers={"content-type": content_type, **(headers or {})}
    )


def _redirect(location: str, *, status: int = 302):
    return httpx.Response(status, headers={"location": location}, text="")


# --- Erfolgsfall & Metadaten -----------------------------------------------------------


async def test_erfolgreicher_abruf_liefert_html_und_metadaten():
    engine = _make_engine({"https://example.com/artikel": _page(HTML_PAGE)})
    result = await engine.fetch("https://example.com/artikel")
    assert result.status == 200
    assert result.final_url == "https://example.com/artikel"
    assert result.title == "ZENJI Testseite"
    assert result.metadata["canonical"] == "https://example.com/kanonisch"
    assert result.metadata["description"] == "Testbeschreibung"
    assert result.metadata["author"] == "Max Mustermann"
    assert result.via_playwright is False
    assert "Inhalt" in result.html


async def test_user_agent_ist_ehrlich_und_hoeflich():
    seen_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(dict(request.headers))
        return _page(HTML_PAGE)

    engine = BrowserEngine(
        transport=httpx.MockTransport(handler),
        per_host_delay=0.0,
        resolver=_resolver("93.184.216.34"),
    )
    await engine.fetch("https://example.com/a")
    assert "ZENJI" in seen_headers.get("user-agent", "")
    assert "robots" in seen_headers.get("user-agent", "")


async def test_stats_werden_auf_erfolgspfad_gefuehrt():
    engine = _make_engine({"https://example.com/a": _page(HTML_PAGE)})
    await engine.fetch("https://example.com/a")
    assert engine.stats["fetches"] == 1
    assert engine.stats["failures"] == 0
    assert engine.stats["last_fetch_url"] == "https://example.com/a"
    assert engine.stats["last_fetch_at"] is not None


# --- Redirects -------------------------------------------------------------------------


async def test_redirect_kette_wird_gefolgt_und_final_url_gesetzt():
    pages = {
        "https://example.com/eins": _redirect("/zwei"),
        "https://example.com/zwei": _page(HTML_PAGE),
    }
    engine = _make_engine(pages)
    result = await engine.fetch("https://example.com/eins")
    assert result.final_url == "https://example.com/zwei"


async def test_redirect_zu_privatem_ziel_blockiert():
    pages = {
        "https://example.com/start": _redirect("http://192.168.0.5/intern"),
    }
    engine = _make_engine(pages)
    with pytest.raises(WebSecurityError):
        await engine.fetch("https://example.com/start")
    assert engine.stats["failures"] == 1


async def test_zu_viele_redirects_brechen_ab():
    pages = {
        "https://example.com/eins": _redirect("/zwei"),
        "https://example.com/zwei": _redirect("/drei"),
        "https://example.com/drei": _redirect("/vier"),
        "https://example.com/vier": _redirect("/fuenf"),
        "https://example.com/fuenf": _redirect("/sechs"),
        "https://example.com/sechs": _redirect("/sieben"),
    }
    engine = _make_engine(pages)
    with pytest.raises(WebFetchError) as info:
        await engine.fetch("https://example.com/eins")
    assert "Weiterleitungen" in info.value.message


# --- robots.txt -------------------------------------------------------------------------


async def test_robots_disallow_blockiert_abruf():
    robots = {"https://example.com": "User-agent: *\nDisallow: /geheim\n"}
    pages = {
        "https://example.com/geheim": _page(HTML_PAGE),
        "https://example.com/offen": _page(HTML_PAGE),
    }
    engine = _make_engine(pages, robots=robots)
    with pytest.raises(WebSecurityError) as info:
        await engine.fetch("https://example.com/geheim")
    assert "robots.txt" in info.value.message
    # Erlaubter Pfad funktioniert weiterhin:
    result = await engine.fetch("https://example.com/offen")
    assert result.status == 200


async def test_robots_txt_wird_pro_origin_gecacht():
    robots = {"https://example.com": "User-agent: *\nDisallow: /geheim\n"}
    pages = {
        "https://example.com/eins": _page(HTML_PAGE),
        "https://example.com/zwei": _page(HTML_PAGE),
    }
    engine = _make_engine(pages, robots=robots)
    await engine.fetch("https://example.com/eins")
    await engine.fetch("https://example.com/zwei")
    robots_calls = [c for c in engine._handler.calls if c.endswith("/robots.txt")]  # type: ignore[attr-defined]
    assert len(robots_calls) == 1


async def test_fehlende_robots_txt_ist_fail_open():
    engine = _make_engine({"https://example.com/a": _page(HTML_PAGE)})
    result = await engine.fetch("https://example.com/a")
    assert result.status == 200


# --- Zugriffsbeschränkungen (kein Umgehen!) -----------------------------------------------


@pytest.mark.parametrize("status", [401, 402, 403, 429])
async def test_zugriffsverweigerung_ohne_umgehungsversuch(status):
    pages = {"https://example.com/lock": _page("gesperrt", status=status)}
    engine = _make_engine(pages)
    with pytest.raises(WebFetchError) as info:
        await engine.fetch("https://example.com/lock")
    assert "umgeht keine" in info.value.message
    # Genau **ein** Abrufversuch der Seite (robots.txt einmalig davor):
    page_calls = [c for c in engine._handler.calls if "/lock" in c]  # type: ignore[attr-defined]
    assert len(page_calls) == 1


async def test_serverfehler_ist_verstaendliche_meldung():
    engine = _make_engine({"https://example.com/boom": _page("kaputt", status=500)})
    with pytest.raises(WebFetchError) as info:
        await engine.fetch("https://example.com/boom")
    assert "HTTP 500" in info.value.message


# --- Limits -------------------------------------------------------------------------------


async def test_groessenlimit_kuerzt_und_markiert():
    big_body = "x" * 5000
    engine = _make_engine(
        {"https://example.com/gross": _page(f"<html><body>{big_body}</body></html>")},
        max_bytes=100,
    )
    result = await engine.fetch("https://example.com/gross")
    assert result.truncated is True
    assert len(result.html) == 100


async def test_nicht_unterstuetzter_content_type_blockiert():
    engine = _make_engine(
        {"https://example.com/doc.pdf": _page("%PDF", content_type="application/pdf")}
    )
    with pytest.raises(WebFetchError) as info:
        await engine.fetch("https://example.com/doc.pdf")
    assert "Inhaltstyp" in info.value.message


async def test_timeout_und_zu_grosse_antworten_grenziert():
    assert ssrf.MAX_RESPONSE_BYTES <= 5_000_000
    assert ssrf.DEFAULT_TIMEOUT_S <= 30


# --- SSRF beim Einstieg --------------------------------------------------------------------


async def test_privater_zielhost_wird_vor_abruf_blockiert():
    engine = _make_engine({})
    with pytest.raises(WebSecurityError):
        await engine.fetch("http://10.1.2.3/intern")
    assert engine.stats["fetches"] == 0
    assert engine.stats["failures"] == 1


async def test_dns_rebinding_bei_hop_wird_abgewiesen():
    pages = {"https://example.com/x": _page(HTML_PAGE)}
    engine = _make_engine(pages, resolver=_resolver("10.0.0.9"))
    with pytest.raises(WebSecurityError):
        await engine.fetch("https://example.com/x")


# --- Höflichkeits-Abstand --------------------------------------------------------------------


async def test_hoeflichkeits_delay_wird_eingehalten():
    engine = _make_engine(
        {
            "https://example.com/a": _page(HTML_PAGE),
            "https://example.com/b": _page(HTML_PAGE),
        },
        per_host_delay=0.05,
    )
    await engine.fetch("https://example.com/a")
    started = time.perf_counter()
    await engine.fetch("https://example.com/b")
    elapsed = time.perf_counter() - started
    assert elapsed >= 0.04


# --- Playwright-Status (ehrlich) ---------------------------------------------------------------


def test_status_meldet_playwright_ehrlich():
    engine = _make_engine({})
    status = engine.status()
    assert status["httpx"]["available"] is True
    # In dieser Testumgebung ist Playwright absichtlich NICHT installiert:
    if not status["playwright"]["available"]:
        assert "nicht installiert" in status["playwright"]["detail"]
    assert status["robots_respected"] is True
    assert status["per_host_delay_s"] == 0.0
