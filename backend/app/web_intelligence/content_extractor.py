"""Content Extraction Engine – saubere Webseiteninhalte für das Modell (Phase 3).

Primär **Trafilatura** (Boilerplate-Entfernung: Navigation, Werbung, Footer,
Cookie-Banner), ergänzend **BeautifulSoup** als Fallback und für Struktur
(Überschriften, Listen, Tabellen, Metadaten).

Erzeugnis: normalisierter, limitierter Text (:class:`ExtractedContent`),
der ausschließlich als **Informationsmaterial** (untrusted data) in den
Modellkontext gelangt – die Ummantelung als Datenblock übernimmt der
Aufrufer (Research Engine / Context Engine).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit

from app.core.logging import get_logger
from app.web_intelligence import ssrf
from app.web_intelligence.search_engine import domain_of, parse_published

log = get_logger("content_extractor")

#: Standardlimit pro Quelle (Zeichen).
DEFAULT_MAX_CHARS = 8_000
#: Mindestlänge, ab der Trafilatura-Output als brauchbarer Haupttext gilt.
MIN_MAIN_TEXT_CHARS = 60
#: Struktur-Limits gegen Kontext-Explosionen.
MAX_HEADINGS = 30
MAX_LISTS = 10
MAX_LIST_ITEMS = 30
MAX_TABLES = 5
MAX_TABLE_ROWS = 40

#: Heuristik für Seitenschrott (Cookie-Banner, Werbung, Social-Widgets).
_JUNK_CLASS = re.compile(
    r"cookie|consent|banner|advert|ads?[-_]|promotion|promo|newsletter|"
    r"social[-_]?share|sharing|popup|overlay|subscribe",
    re.IGNORECASE,
)

_META_DATE_KEYS = (
    "article:published_time",
    "og:published_time",
    "date",
    "pubdate",
    "publishdate",
    "dc.date",
    "sailthru.date",
)
_META_AUTHOR_KEYS = ("author", "article:author", "dc.creator", "parsely-author", "byl")


@dataclass(slots=True)
class ExtractedContent:
    """Normalisierter, begrenzter Seiteninhalt einer Quelle."""

    url: str
    domain: str
    title: str
    text: str
    extractor: str  # "trafilatura" | "beautifulsoup"
    headings: list[str] = field(default_factory=list)
    list_items: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    author: str | None = None
    published_at: datetime | None = None
    canonical_url: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    truncated: bool = False

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "domain": self.domain,
            "title": self.title,
            "text": self.text,
            "extractor": self.extractor,
            "headings": list(self.headings),
            "list_items": list(self.list_items),
            "tables": list(self.tables),
            "author": self.author,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "canonical_url": self.canonical_url,
            "metadata": dict(self.metadata),
            "truncated": self.truncated,
        }

    def context_text(self, *, max_chars: int = DEFAULT_MAX_CHARS) -> str:
        """Modellgeeigneter, begrenzter Text (Inhaltsdaten, keine Anweisungen)."""
        parts = [
            f"QUELLE: {self.url}",
            f"TITEL: {self.title}",
            f"DOMAIN: {self.domain}",
        ]
        if self.author:
            parts.append(f"AUTOR: {self.author}")
        if self.published_at:
            parts.append(f"VERÖFFENTLICHT: {self.published_at.date().isoformat()}")
        parts.append("")
        parts.append(self.text)
        extras: list[str] = []
        if self.headings:
            extras.append("Überschriften: " + " | ".join(self.headings[:MAX_HEADINGS]))
        if self.list_items:
            extras.append("Listenpunkte: " + " | ".join(self.list_items[:MAX_LIST_ITEMS]))
        if self.tables:
            extras.append("Tabellen: " + " / ".join(self.tables[:MAX_TABLES]))
        if extras:
            parts.append("")
            parts.append("[STRUKTURHINWEISE]")
            parts.extend(extras)
        joined = "\n".join(parts)
        if len(joined) > max_chars:
            joined = joined[:max_chars].rstrip() + " …"
        return joined


class ContentExtractor:
    """Extrahiert Hauptinhalt + Struktur aus HTML (Trafilatura → BS4-Fallback)."""

    name = "content_extractor"

    def extract(
        self,
        html: str,
        url: str,
        *,
        max_chars: int = DEFAULT_MAX_CHARS,
        engine: str | None = None,
    ) -> ExtractedContent:
        """Extrahiert Inhalte.

        ``engine=None``: Trafilatura primär, BS4-Fallback bei Mageroutput.
        ``engine="beautifulsoup"``: erzwingt den BS4-Pfad (Tests/Fallback).
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html or "", "html.parser")
        metadata = self._collect_metadata(soup)
        headings = self._collect_headings(soup)
        list_items, tables = self._collect_structure(soup)
        canonical = self._resolve_canonical(soup, url)
        title = self._resolve_title(soup, metadata, url)
        author, published = self._resolve_author_date(metadata, soup)

        text, used = self._main_text(soup, html, engine)
        truncated = False
        if len(text) > max_chars:
            text = text[:max_chars].rsplit(" ", 1)[0] if " " in text[:max_chars] else text[:max_chars]
            truncated = True

        return ExtractedContent(
            url=url,
            domain=domain_of(url),
            title=title,
            text=text,
            extractor=used,
            headings=headings,
            list_items=list_items,
            tables=tables,
            author=author,
            published_at=published,
            canonical_url=canonical,
            metadata=metadata,
            truncated=truncated,
        )

    # --- Haupttext ------------------------------------------------------------------

    def _main_text(self, soup, html: str, engine: str | None) -> tuple[str, str]:
        """Trafilatura primär; BS4-Fallback bei Nichtergebnis oder erzwungen."""
        if engine in (None, "trafilatura"):
            text = self._trafilatura_text(html)
            if text and len(text) >= MIN_MAIN_TEXT_CHARS:
                return text, "trafilatura"
        return self._bs4_text(soup), "beautifulsoup"

    @staticmethod
    def _trafilatura_text(html: str) -> str:
        """Trafilatura-Extraktion (Boilerplate entfernt). Fehler → leerer Text."""
        try:
            import trafilatura

            result = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,
                favor_recall=True,
            )
        except ImportError:
            return ""
        except Exception as exc:  # noqa: BLE001 – Extraktion darf nie hart scheitern
            log.debug("Trafilatura-Fehler: %s", exc)
            return ""
        return (result or "").strip()

    @staticmethod
    def _bs4_text(soup) -> str:
        """BS4-Fallback: Seitenschrott entfernen, Fließtext normalisieren."""
        for tag in soup(["script", "style", "noscript", "template", "iframe", "svg", "form", "button"]):
            tag.decompose()
        for tag in soup.find_all(["nav", "footer", "header", "aside"]):
            tag.decompose()
        # Cookie-Banner / Werbeblöcke per Klassen-Heuristik:
        for tag in soup.find_all(attrs={"class": _JUNK_CLASS}):
            tag.decompose()
        for tag in soup.find_all(attrs={"id": _JUNK_CLASS}):
            tag.decompose()
        root = soup.body or soup
        lines = [line.strip() for line in root.get_text("\n").splitlines()]
        return "\n".join(line for line in lines if line)

    # --- Struktur & Metadaten ----------------------------------------------------------

    @staticmethod
    def _collect_metadata(soup) -> dict[str, str]:
        meta: dict[str, str] = {}
        for tag in soup.find_all("meta"):
            key = tag.get("property") or tag.get("name") or ""
            content = tag.get("content")
            if key and content:
                meta[key.strip().lower()] = str(content).strip()[:500]
        return meta

    @staticmethod
    def _collect_headings(soup) -> list[str]:
        headings: list[str] = []
        for level in ("h1", "h2", "h3", "h4"):
            for tag in soup.find_all(level):
                text = " ".join(tag.get_text(" ").split())
                if text and text not in headings:
                    headings.append(text)
                if len(headings) >= MAX_HEADINGS:
                    return headings
        return headings

    @staticmethod
    def _collect_structure(soup) -> tuple[list[str], list[str]]:
        """Listenpunkte und Tabellenzeilen (begrenzt, duplikatfrei)."""
        list_items: list[str] = []
        for ul in soup.find_all(["ul", "ol"]):
            for li in ul.find_all("li", recursive=False):
                text = " ".join(li.get_text(" ").split())
                if text and text not in list_items:
                    list_items.append(text)
                if len(list_items) >= MAX_LIST_ITEMS:
                    return list_items, _collect_tables(soup)
        return list_items, _collect_tables(soup)

    @staticmethod
    def _resolve_canonical(soup, url: str) -> str | None:
        link = soup.find("link", rel=lambda v: bool(v) and "canonical" in v)
        href = link.get("href") if link else None
        absolute = ssrf.absolute_url(url, href)
        return absolute if absolute and absolute.startswith(("http://", "https://")) else None

    @staticmethod
    def _resolve_title(soup, metadata: dict[str, str], url: str) -> str:
        if metadata.get("og:title"):
            return metadata["og:title"]
        h1 = soup.find("h1")
        if h1:
            text = " ".join(h1.get_text(" ").split())
            if text:
                return text
        if soup.title and soup.title.string:
            text = " ".join(soup.title.string.split())
            if text:
                return text
        return domain_of(url) or "Ohne Titel"

    @staticmethod
    def _resolve_author_date(metadata: dict[str, str], soup) -> tuple[str | None, datetime | None]:
        author: str | None = None
        for key in _META_AUTHOR_KEYS:
            if metadata.get(key):
                author = metadata[key]
                break
        if not author:
            time_tag = soup.find("time", attrs={"datetime": True})
            if time_tag:
                published = parse_published(time_tag["datetime"])
            else:
                published = None
        else:
            published = None
        if published is None:
            for key in _META_DATE_KEYS:
                if metadata.get(key):
                    published = parse_published(metadata[key])
                    if published:
                        break
        return author, published


def _collect_tables(soup) -> list[str]:
    """Tabellenzeilen als 'Zelle | Zelle'-Strings (begrenzt)."""
    tables: list[str] = []
    for table in soup.find_all("table"):
        rows: list[str] = []
        for tr in table.find_all("tr"):
            cells = [" ".join(cell.get_text(" ").split()) for cell in tr.find_all(["th", "td"])]
            row = " | ".join(cell for cell in cells if cell)
            if row:
                rows.append(row)
            if len(rows) >= MAX_TABLE_ROWS:
                break
        if rows:
            tables.append(" ; ".join(rows))
        if len(tables) >= MAX_TABLES:
            break
    return tables


__all__ = [
    "DEFAULT_MAX_CHARS",
    "ExtractedContent",
    "ContentExtractor",
]
