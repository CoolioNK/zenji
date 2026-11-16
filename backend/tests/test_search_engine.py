"""Tests: Search Engine (Phase 3) – Provider, Normalisierung, Dedupe, Fehler.

Alle Tests laufen ohne echten Netzwerkzugriff: SearXNG/Brave werden über
``httpx.MockTransport`` simuliert.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core.exceptions import SearchProviderError, ValidationError
from app.web_intelligence.search_engine import (
    SearchEngine,
    SearXNGProvider,
    BraveProvider,
    canonical_url,
    domain_of,
    merge_results,
    parse_published,
)


def _searxng_transport(payload: dict | None = None, *, status: int = 200, body: str | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if body is not None:
            return httpx.Response(status, text=body)
        return httpx.Response(status, json=payload or {"results": []})

    return httpx.MockTransport(handler)


def _result(url: str, title: str, snippet: str = "Text", **extra):
    entry = {"url": url, "title": title, "content": snippet}
    entry.update(extra)
    return entry


# --- Normalisierung -------------------------------------------------------------------


async def test_ergebnisse_werden_normalisiert():
    provider = SearXNGProvider(
        "http://localhost:8888",
        transport=_searxng_transport(
            {"results": [_result("https://example.com/Artikel/", "  Titel  ", "  Ein Snippet ")]}
        ),
    )
    engine = SearchEngine({"searxng": provider})
    results = await engine.search("test", limit=10)
    assert len(results) == 1
    entry = results[0]
    assert entry.title == "Titel"
    assert entry.domain == "example.com"
    assert entry.snippet == "Ein Snippet"
    assert entry.url == "https://example.com/Artikel/"
    assert entry.provider == "searxng"
    assert entry.query == "test"
    assert isinstance(entry.retrieved_at, datetime)
    assert entry.published_at is None


async def test_nur_http_und_https_ergebnisse_werden_uebernommen():
    payload = {
        "results": [
            _result("https://ok.example/a", "OK"),
            _result("ftp://skip.example/b", "Skip"),
            _result("javascript:void(0)", "Skip2"),
            {"title": "Ohne URL"},
        ]
    }
    provider = SearXNGProvider("http://x", transport=_searxng_transport(payload))
    engine = SearchEngine({"searxng": provider})
    results = await engine.search("q")
    assert [r.title for r in results] == ["OK"]


async def test_doppelte_urls_werden_entfernt():
    payload = {
        "results": [
            _result("https://example.com/a", "Erster"),
            _result("https://example.com/a#fragment", "Duplikat-Fragment"),
            _result("https://example.com/a/", "Duplikat-Slash"),
            _result("https://example.com/b", "Anders"),
        ]
    }
    engine = SearchEngine({"searxng": SearXNGProvider("http://x", transport=_searxng_transport(payload))})
    results = await engine.search("q")
    assert [r.title for r in results] == ["Erster", "Anders"]


async def test_doppelte_domain_titel_werden_entfernt():
    payload = {
        "results": [
            _result("https://example.com/p1", "Gleicher Titel"),
            _result("https://example.com/p2", "Gleicher Titel"),
        ]
    }
    engine = SearchEngine({"searxng": SearXNGProvider("http://x", transport=_searxng_transport(payload))})
    results = await engine.search("q")
    assert len(results) == 1


async def test_veroeffentlichungsdatum_wird_uebernommen():
    iso = "2026-11-01T10:00:00+00:00"
    payload = {"results": [_result("https://a.example/1", "A", published_at=iso)]}
    engine = SearchEngine({"searxng": SearXNGProvider("http://x", transport=_searxng_transport(payload))})
    result = (await engine.search("q"))[0]
    assert result.published_at is not None
    assert result.published_at.year == 2026


async def test_relverweis_alter_wird_geparst():
    parsed = parse_published("2 days ago")
    assert parsed is not None
    delta = datetime.now(UTC) - parsed
    assert timedelta(days=1) < delta < timedelta(days=3)


async def test_limit_wird_durchgesetzt():
    payload = {"results": [_result(f"https://a.example/{i}", f"T{i}") for i in range(20)]}
    engine = SearchEngine({"searxng": SearXNGProvider("http://x", transport=_searxng_transport(payload))})
    results = await engine.search("q", limit=5)
    assert len(results) == 5


# --- Fehlerbehandlung -----------------------------------------------------------------


async def test_provider_nicht_erreichbar_gibt_verstaendliche_meldung():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Verbindung verweigert")

    provider = SearXNGProvider("http://localhost:8888", transport=httpx.MockTransport(handler))
    engine = SearchEngine({"searxng": provider})
    with pytest.raises(SearchProviderError) as info:
        await engine.search("test")
    assert "nicht erreichbar" in info.value.message
    assert "SearXNG-Dienst" in info.value.message  # Handlungshinweis


async def test_searxng_html_statt_json_gibt_klarfehler():
    provider = SearXNGProvider(
        "http://localhost:8888",
        transport=_searxng_transport(status=200, body="<html>JSON-Modus aus</html>"),
    )
    engine = SearchEngine({"searxng": provider})
    with pytest.raises(SearchProviderError) as info:
        await engine.search("test")
    assert "JSON" in info.value.message


async def test_searxng_403_hinweis_auf_formats():
    provider = SearXNGProvider(
        "http://localhost:8888", transport=_searxng_transport(status=403, body="forbidden")
    )
    engine = SearchEngine({"searxng": provider})
    with pytest.raises(SearchProviderError) as info:
        await engine.search("test")
    assert "formats" in info.value.message


async def test_searxng_serverfehler():
    provider = SearXNGProvider(
        "http://localhost:8888", transport=_searxng_transport(status=500, body="boom")
    )
    engine = SearchEngine({"searxng": provider})
    with pytest.raises(SearchProviderError) as info:
        await engine.search("q")
    assert "500" in info.value.message


async def test_leere_suchanfrage_abgelehnt():
    engine = SearchEngine({"searxng": SearXNGProvider("http://x")})
    with pytest.raises(ValidationError):
        await engine.search("   ")


def test_unbekannter_provider_abgelehnt():
    engine = SearchEngine({"searxng": SearXNGProvider("http://x")})
    with pytest.raises(ValidationError) as info:
        engine.provider("mystery")
    assert "searxng" in info.value.message


# --- Brave-Provider --------------------------------------------------------------------


async def test_brave_provider_normalisiert():
    payload = {"web": {"results": [_result("https://b.example/x", "Brave-Titel", description="Desc")]}}

    class Capture(httpx.MockTransport):
        def __init__(self):
            super().__init__(self._handle)
            self.seen_headers: dict[str, str] = {}

        def _handle(self, request: httpx.Request) -> httpx.Response:
            self.seen_headers = dict(request.headers)
            return httpx.Response(200, json=payload)

    transport = Capture()
    provider = BraveProvider("key-123", transport=transport)
    results = await provider.search("q", limit=5)
    assert transport.seen_headers.get("x-subscription-token") == "key-123"
    assert results[0]["title"] == "Brave-Titel"

    engine = SearchEngine({"brave": provider})
    normalized = (await engine.search("q", provider="brave"))[0]
    assert normalized.domain == "b.example"


async def test_brave_ohne_api_key_gibt_klarfehler():
    provider = BraveProvider("", transport=_searxng_transport())
    with pytest.raises(SearchProviderError) as info:
        await provider.search("q", limit=5)
    assert "API-Key" in info.value.message


async def test_brave_rate_limit():
    provider = BraveProvider("k", transport=_searxng_transport(status=429, body="rate"))
    with pytest.raises(SearchProviderError) as info:
        await provider.search("q", limit=5)
    assert "Ratenlimit" in info.value.message


# --- Cross-Query-Merge -----------------------------------------------------------------


def test_merge_results_dedupliziert_ueber_anfragen_hinweg():
    batch1 = [
        _sr("https://a.example/1", "A1", 1, "q1"),
        _sr("https://a.example/2", "A2", 2, "q1"),
    ]
    batch2 = [
        _sr("https://a.example/1#top", "A1-Duplikat", 1, "q2"),
        _sr("https://b.example/9", "B9", 1, "q2"),
    ]
    merged = merge_results(batch1, batch2)
    assert [r.url for r in merged] == ["https://a.example/1", "https://a.example/2", "https://b.example/9"]


def _sr(url: str, title: str, rank: int, query: str):
    from app.web_intelligence.search_engine import SearchResult

    return SearchResult(
        id=f"t:{rank}",
        title=title,
        url=url,
        domain=domain_of(url),
        snippet="",
        query=query,
        provider="fake",
        retrieved_at=datetime.now(UTC),
        rank=rank,
    )


# --- Helfer ------------------------------------------------------------------------------


def test_canonical_url_normalisiert_fuer_vergleich():
    assert (
        canonical_url("https://Example.com:443/Pfad/?b=2&a=1#top")
        == canonical_url("https://example.com/Pfad?a=1&b=2")
    )


def test_domain_of_entfernt_www():
    assert domain_of("https://WWW.Example.com/x") == "example.com"
    assert domain_of("kein url") == ""


# --- Verbindungstest ----------------------------------------------------------------------


async def test_provider_status_erfolgreich():
    provider = SearXNGProvider(
        "http://localhost:8888",
        transport=_searxng_transport({"results": [_result("https://a.example/1", "T")]}),
    )
    status = await provider.status()
    assert status["available"] is True


async def test_provider_status_meldet_ausfall():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    provider = SearXNGProvider("http://localhost:8888", transport=httpx.MockTransport(handler))
    status = await provider.status()
    assert status["available"] is False
    assert "nicht erreichbar" in status["detail"]
