"""Tests: Content Extraction (Phase 3) – Trafilatura primär, BS4-Fallback, Limits."""

from __future__ import annotations

import pytest

from app.web_intelligence.content_extractor import (
    DEFAULT_MAX_CHARS,
    ContentExtractor,
    ExtractedContent,
)

ARTICLE_HTML = """<html>
<head>
  <title>Artikel-Titel</title>
  <link rel="canonical" href="/kanonisch">
  <meta name="author" content="Max Mustermann">
  <meta property="article:published_time" content="2026-11-01T10:00:00+00:00">
</head>
<body>
  <nav><a href="/">Startseite</a> <a href="/impressum">Impressum</a></nav>
  <div class="cookie-banner">Wir verwenden Cookies.</div>
  <article>
    <h1>Transformer einfach erklärt</h1>
    <h2>Einführung</h2>
    <p>Transformer-Modelle verarbeiten Sequenzen mit Aufmerksamkeitsmechanismen
    und bilden die Grundlage moderner Sprachmodelle.</p>
    <ul><li>Punkt A</li><li>Punkt B</li></ul>
    <table><tr><th>Name</th><th>Wert</th></tr><tr><td>Alpha</td><td>42</td></tr></table>
    <h2>Details</h2>
    <p>Der Aufmerksamkeitsmechanismus gewichtet Token kontextabhängig.</p>
  </article>
  <footer>© 2026 Beispielverlag. Alle Rechte vorbehalten.</footer>
</body>
</html>"""


@pytest.fixture()
def extractor():
    return ContentExtractor()


# --- Haupttext (Trafilatura primär) ---------------------------------------------------


def test_trafilatura_entfernt_boilerplate(extractor):
    content = extractor.extract(ARTICLE_HTML, "https://example.com/artikel")
    assert content.extractor == "trafilatura"
    assert "Transformer-Modelle verarbeiten" in content.text
    assert "Aufmerksamkeitsmechanismus" in content.text
    # Boilerplate raus:
    assert "Startseite" not in content.text
    assert "Impressum" not in content.text
    assert "© 2026" not in content.text


def test_cookie_banner_wird_entfernt(extractor):
    content = extractor.extract(ARTICLE_HTML, "https://example.com/artikel")
    assert "Wir verwenden Cookies" not in content.text
    assert "Alle Rechte vorbehalten" not in content.text


# --- Struktur (BS4, immer) ---------------------------------------------------------------


def test_headings_listen_tabellen_werden_gesammelt(extractor):
    content = extractor.extract(ARTICLE_HTML, "https://example.com/artikel")
    assert "Transformer einfach erklärt" in content.headings
    assert "Einführung" in content.headings
    assert "Details" in content.headings
    assert "Punkt A" in content.list_items
    assert "Punkt B" in content.list_items
    assert any("Alpha | 42" in table for table in content.tables)


def test_metadaten_autor_datum_canonical(extractor):
    content = extractor.extract(ARTICLE_HTML, "https://example.com/artikel")
    assert content.author == "Max Mustermann"
    assert content.published_at is not None
    assert content.published_at.year == 2026
    assert content.canonical_url == "https://example.com/kanonisch"
    assert content.domain == "example.com"


def test_canonical_rel_wird_absolut(extractor):
    content = extractor.extract(
        '<html><head><link rel="canonical" href="/a/b"></head><body><p>' + "x" * 200 + "</p></body></html>",
        "https://example.com/start",
    )
    assert content.canonical_url == "https://example.com/a/b"


# --- Titel-Kette ---------------------------------------------------------------------------


def test_titel_og_zuerst_dann_h1_dann_title_tag(extractor):
    content = extractor.extract(
        '<html><head><title>T-Tag</title></head><body><h1>H1-Titel</h1>'
        + "<p>" + "y" * 150 + "</p></body></html>",
        "https://example.com/x",
    )
    assert content.title == "H1-Titel"

    content2 = extractor.extract(
        '<html><head><meta property="og:title" content="OG-Titel"></head>'
        + '<body><h1>H1</h1><p>' + "z" * 150 + "</p></body></html>",
        "https://example.com/x",
    )
    assert content2.title == "OG-Titel"


def test_titel_fallback_domain(extractor):
    content = extractor.extract(
        '<html><body><p>' + "q" * 150 + "</p></body></html>", "https://beispiel.de/x"
    )
    assert content.title == "beispiel.de"


# --- Fallback-Pfad (BS4) ------------------------------------------------------------------


def test_bs4_fallback_bei_mageroutput(extractor):
    tiny = "<html><body><p>kurz</p></body></html>"
    content = extractor.extract(tiny, "https://example.com/kurz")
    # Trafilatura liefert nichts Brauchbares (< 60 Zeichen) → BS4:
    assert content.extractor == "beautifulsoup"
    assert "kurz" in content.text


def test_bs4_erzwungen_entfernt_schrott(extractor):
    html = (
        '<html><body><nav>Menü</nav><div class="advert">Werbung</div>'
        '<p>' + "Inhalt " * 30 + "</p></body></html>"
    )
    content = extractor.extract(html, "https://example.com/x", engine="beautifulsoup")
    assert content.extractor == "beautifulsoup"
    assert "Menü" not in content.text
    assert "Werbung" not in content.text
    assert "Inhalt" in content.text


# --- Limits ---------------------------------------------------------------------------------


def test_max_chars_kuerzt_und_markiert(extractor):
    html = "<html><body><p>" + "Wort " * 3000 + "</p></body></html>"
    content = extractor.extract(html, "https://example.com/lang", max_chars=500)
    assert content.truncated is True
    assert len(content.text) <= 500


def test_standardlimit_ist_gesetzt():
    assert 2000 <= DEFAULT_MAX_CHARS <= 20_000


# --- Kontexttext (modellgeeignet) ---------------------------------------------------------------


def test_context_text_enthaelt_bausteine(extractor):
    content = extractor.extract(ARTICLE_HTML, "https://example.com/artikel")
    text = content.context_text()
    assert text.startswith("QUELLE: https://example.com/artikel")
    assert "TITEL:" in text
    assert "DOMAIN: example.com" in text
    assert "AUTOR: Max Mustermann" in text
    assert "VERÖFFENTLICHT: 2026-11-01" in text
    assert "[STRUKTURHINWEISE]" in text


def test_context_text_respektiert_limit(extractor):
    content = extractor.extract(ARTICLE_HTML, "https://example.com/artikel")
    bounded = content.context_text(max_chars=300)
    assert len(bounded) <= 310  # Limit + Ellipsen-Toleranz
    assert bounded.endswith("…") or len(bounded) <= 300


def test_as_dict_ist_serialisierbar(extractor):
    content = extractor.extract(ARTICLE_HTML, "https://example.com/artikel")
    data = content.as_dict()
    assert data["extractor"] == "trafilatura"
    assert isinstance(data, dict)
    assert isinstance(content, ExtractedContent)
