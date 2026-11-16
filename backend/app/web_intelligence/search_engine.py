"""Search Engine – flexible Suchmaschinen-Abstraktion (Phase 3).

Provider-Architektur: Die Engine kennt nur das :class:`SearchProvider`-
Protokoll; konkrete Anbieter (SearXNG, Brave Search API) registrieren sich
daran. Alle Ergebnisse werden in ein einheitliches internes Format
(:class:`SearchResult`) normalisiert: Titel, URL, Domain, Snippet,
Veröffentlichungsdatum (falls verfügbar), Suchanfrage, Provider,
Abrufzeitpunkt.

Sicherheit/Robustheit:

- Nur http(s)-Ergebnis-URLs werden übernommen (Rest verworfen).
- Deduplizierung über normalisierte URL **und** Domain+Titel.
- Timeouts und Limits sind konfigurierbar; Provider-Ausfälle erzeugen
  verständliche :class:`SearchProviderError`-Meldungen (kein Stacktrace
  für den Nutzer).
- Der Suchanbieter-Endpunkt ist **Nutzereinstellung** (wie der Ollama-Endpunkt)
  und daher bewusst nicht Teil des SSRF-Webabruf-Schutzes; Antwortgrößen
  sind trotzdem begrenzt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from app.core.exceptions import SearchProviderError, ValidationError
from app.core.logging import get_logger

log = get_logger("search_engine")

#:Maximale Anzahl Suchergebnisse pro Einzelanfrage (hartes Limit).
MAX_RESULTS_PER_QUERY = 20
#: Maximale Antwortgröße einer Such-API (Schutz gegen übergroße Antworten).
MAX_SEARCH_RESPONSE_BYTES = 2_000_000
DEFAULT_SEARCH_TIMEOUT_S = 15.0

_RELATIVE_AGE = re.compile(r"(\d+)\s*(minute|hour|day|week|month|year)", re.IGNORECASE)
_AGE_UNIT_S = {
    "minute": 60,
    "hour": 3600,
    "day": 86400,
    "week": 604800,
    "month": 2_592_000,
    "year": 31_536_000,
}


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Normalisiertes Suchergebnis (einheitliches internes Format)."""

    id: str
    title: str
    url: str
    domain: str
    snippet: str
    query: str
    provider: str
    retrieved_at: datetime
    published_at: datetime | None = None
    rank: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "domain": self.domain,
            "snippet": self.snippet,
            "query": self.query,
            "provider": self.provider,
            "retrieved_at": self.retrieved_at.isoformat(),
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "rank": self.rank,
        }


class SearchProvider(Protocol):
    """Protokoll für Suchanbieter (z. B. SearXNG, Brave)."""

    name: str

    async def search(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        """Liefert rohe Ergebnis-Dicts (url/title/snippet/published …)."""
        ...

    async def status(self) -> dict[str, Any]:
        """Verfügbarkeitstest (Verbindungstest im Control Center)."""
        ...


def domain_of(url: str) -> str:
    """Domain eines URLs (kleingeschrieben, ohne www.-Präfix)."""
    try:
        hostname = urlsplit(url).hostname or ""
    except ValueError:
        return ""
    hostname = hostname.lower().rstrip(".")
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname


def canonical_url(url: str) -> str:
    """Vergleichsnormalisierung eines URLs (ohne Fragment/Trailing-Slash)."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url.strip().lower()
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    # Standardports fallen weg (443 bei https, 80 bei http):
    if port is not None and not (
        (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    ):
        netloc = f"{host}:{port}"
    else:
        netloc = host
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    query = "&".join(sorted(filter(None, parts.query.split("&"))))
    return f"{scheme}://{netloc}{path}" + (f"?{query}" if query else "")


def parse_published(raw: Any) -> datetime | None:
    """Best-effort-Veröffentlichungsdatum (ISO oder relative Angabe)."""
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    # ISO-8601 / ähnliche Formate:
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    except ValueError:
        pass
    # Relative Altersangaben ("2 days ago", "vor 3 Stunden" wird vorher
    # vom Provider auf "2 days ago" gemappt):
    match = _RELATIVE_AGE.search(text)
    if match:
        amount, unit = int(match.group(1)), match.group(2).lower()
        from datetime import timedelta

        return datetime.now(UTC) - timedelta(seconds=amount * _AGE_UNIT_S.get(unit, 0))
    return None


class SearXNGProvider:
    """Suchanbieter für eine **lokale** SearXNG-Instanz (JSON-API).

    Standardmäßig wird ein lokal betriebener Dienst erwartet
    (``http://localhost:8888``); die Adresse ist Nutzereinstellung.  Der
    JSON-Modus muss in der SearXNG-Konfiguration aktiv sein
    (``formats: [html, json]``).
    """

    name = "searxng"

    def __init__(
        self,
        base_url: str = "http://localhost:8888",
        *,
        timeout: float = DEFAULT_SEARCH_TIMEOUT_S,
        language: str = "de",
        transport: httpx.AsyncTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.language = language
        self._transport = transport

    async def search(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        params = {
            "q": query,
            "format": "json",
            "language": self.language,
            "safesearch": 0,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, transport=self._transport, follow_redirects=True
            ) as client:
                response = await client.get(f"{self.base_url}/search", params=params)
        except httpx.HTTPError as exc:
            raise SearchProviderError(
                f"Suchanbieter SearXNG ist nicht erreichbar unter {self.base_url}. "
                "Prüfe, ob der lokale SearXNG-Dienst läuft (z. B. via Docker).",
                detail={"base_url": self.base_url, "reason": type(exc).__name__},
            ) from exc
        if response.status_code == 403:
            raise SearchProviderError(
                "SearXNG lehnt die JSON-API ab (403). Aktiviere im SearXNG-"
                "Settings 'formats: [html, json]' oder nutze einen anderen Anbieter.",
            )
        if response.status_code >= 400:
            raise SearchProviderError(
                f"SearXNG antwortete mit HTTP {response.status_code}.",
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise SearchProviderError(
                "SearXNG lieferte keine gültige JSON-Antwort "
                "(HTML statt JSON deutet auf deaktivierten JSON-Modus hin)."
            ) from exc
        results = payload.get("results", []) if isinstance(payload, dict) else []
        if not isinstance(results, list):
            results = []
        return results[:limit]

    async def status(self) -> dict[str, Any]:
        try:
            await self.search("zenji verbindungstest", limit=1)
        except SearchProviderError as exc:
            return {"available": False, "detail": exc.message}
        return {"available": True, "detail": f"Verbunden: {self.base_url}"}


class BraveProvider:
    """Brave Search API (Data-for-Web-Plan, API-Key erforderlich)."""

    name = "brave"

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = DEFAULT_SEARCH_TIMEOUT_S,
        transport: httpx.AsyncTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self._transport = transport

    async def search(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        if not self.api_key:
            raise SearchProviderError(
                "Brave Search ist als Anbieter gewählt, aber kein API-Key "
                "konfiguriert (Web-Einstellungen im Control Center)."
            )
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                transport=self._transport,
                follow_redirects=True,
                headers=headers,
            ) as client:
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": limit},
                )
        except httpx.HTTPError as exc:
            raise SearchProviderError(
                f"Brave Search ist nicht erreichbar ({type(exc).__name__})."
            ) from exc
        if response.status_code == 401:
            raise SearchProviderError("Brave Search lehnt den API-Key ab (401).")
        if response.status_code == 429:
            raise SearchProviderError(
                "Brave Search: Ratenlimit erreicht (429) – später erneut versuchen."
            )
        if response.status_code >= 400:
            raise SearchProviderError(
                f"Brave Search antwortete mit HTTP {response.status_code}."
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise SearchProviderError("Brave Search lieferte keine JSON-Antwort.") from exc
        web = payload.get("web", {}) if isinstance(payload, dict) else {}
        results = web.get("results", []) if isinstance(web, dict) else []
        return results[:limit] if isinstance(results, list) else []

    async def status(self) -> dict[str, Any]:
        try:
            await self.search("zenji verbindungstest", limit=1)
        except SearchProviderError as exc:
            return {"available": False, "detail": exc.message}
        return {"available": True, "detail": "Brave Search verbunden."}


class SearchEngine:
    """Normalisiert, dedupliziert und begrenzt Ergebnisse aller Provider."""

    name = "search"

    def __init__(
        self,
        providers: dict[str, SearchProvider],
        *,
        default_provider: str = "searxng",
    ) -> None:
        self._providers = providers
        self._default = default_provider

    @property
    def provider_names(self) -> list[str]:
        return list(self._providers)

    def provider(self, name: str | None = None) -> SearchProvider:
        """Wählt einen Provider (Default bei leer/None); Unbekannter → Fehler."""
        key = (name or "").strip().lower() or self._default
        provider = self._providers.get(key)
        if provider is None:
            raise ValidationError(
                f"Unbekannter Suchanbieter '{key}'. Verfügbar: {sorted(self._providers)}."
            )
        return provider

    async def search(
        self,
        query: str,
        *,
        provider: str | None = None,
        limit: int = 10,
        timeout: float | None = None,
    ) -> list[SearchResult]:
        """Führt **eine** Suchanfrage aus und normalisiert das Ergebnis.

        Ein Ausfall des Anbieters endet in einer verständlichen
        ``SearchProviderError``-Meldung – der Aufrufer (Research Engine)
        entscheidet, ob die Recherche mit Teilergebnissen weiterläuft.
        """
        cleaned = (query or "").strip()
        if not cleaned:
            raise ValidationError("Suchanfrage darf nicht leer sein.")
        limit = max(1, min(limit, MAX_RESULTS_PER_QUERY))
        selected = self.provider(provider)
        started = datetime.now(UTC)
        raw_results = await selected.search(cleaned, limit=limit)
        normalized = self._normalize(
            raw_results, query=cleaned, provider_name=selected.name, started=started
        )
        return normalized[:limit]

    def _normalize(
        self,
        raw_results: list[dict[str, Any]],
        *,
        query: str,
        provider_name: str,
        started: datetime,
    ) -> list[SearchResult]:
        """Rohegebnisse → einheitliche ``SearchResult``-Liste (dedupliziert)."""
        results: list[SearchResult] = []
        seen_urls: set[str] = set()
        seen_domain_titles: set[tuple[str, str]] = set()
        rank = 0
        for index, raw in enumerate(raw_results):
            if not isinstance(raw, dict):
                continue
            url = str(raw.get("url") or "").strip()
            title = _clean_text(raw.get("title") or raw.get("headline"))
            if not url or not url.lower().startswith(("http://", "https://")):
                continue  # kein valides Webelement
            if not title:
                title = domain_of(url) or "Ohne Titel"
            canonical = canonical_url(url)
            if canonical in seen_urls:
                continue
            domain = domain_of(url)
            domain_title = (domain, title.casefold())
            if domain and domain_title in seen_domain_titles:
                continue
            seen_urls.add(canonical)
            seen_domain_titles.add(domain_title)
            rank += 1
            results.append(
                SearchResult(
                    id=f"{provider_name}:{index:03d}",
                    title=title,
                    url=url,
                    domain=domain,
                    snippet=_clean_text(raw.get("snippet") or raw.get("content") or raw.get("description")),
                    query=query,
                    provider=provider_name,
                    retrieved_at=started,
                    published_at=parse_published(
                        raw.get("published_at") or raw.get("publishedDate") or raw.get("age")
                    ),
                    rank=rank,
                )
            )
        return results


def _clean_text(value: Any) -> str:
    """Whitespace aufräumen, HTML-Entities grob entfernen (Snippet-Ebene)."""
    import html

    text = html.unescape(str(value or ""))
    return " ".join(text.split())


def merge_results(*batches: list[SearchResult], limit: int = 50) -> list[SearchResult]:
    """Mehrere Ergebnislisten zusammenführen (cross-query Dedupe)."""
    merged: list[SearchResult] = []
    seen: set[str] = set()
    seen_domain_titles: set[tuple[str, str]] = set()
    for batch in batches:
        for result in batch:
            canonical = canonical_url(result.url)
            domain_title = (result.domain, result.title.casefold())
            if canonical in seen or domain_title in seen_domain_titles:
                continue
            seen.add(canonical)
            seen_domain_titles.add(domain_title)
            merged.append(result)
            if len(merged) >= limit:
                return merged
    return merged


__all__ = [
    "BraveProvider",
    "MAX_RESULTS_PER_QUERY",
    "MAX_SEARCH_RESPONSE_BYTES",
    "SearchEngine",
    "SearchProvider",
    "SearchResult",
    "SearXNGProvider",
    "canonical_url",
    "domain_of",
    "merge_results",
    "parse_published",
]
