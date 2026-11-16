"""Browser Engine – kontrollierter, sicherer Webabruf (Phase 3).

Primär httpx (statische Inhalte).  Reicht das nicht (JavaScript-nötige
Seite, winziger Inhalt), wird **optional** Playwright als Fallback
verwendet – falls installiert; ohne Playwright meldet der Status das
ehrlich („nicht installiert“).

Sicherheitsarchitektur (jeder Abruf, jeder Redirect-Hop):

1. ``ssrf.check_url`` **vor** dem Abruf (Schema, Port, Host, DNS, IPs).
2. ``robots.txt`` des Zielsystems wird respektiert (Cache pro Origin,
   fail-open bei Erreichbarkeitsproblemen, dokumentiert).
3. Höflichkeits-Abstand pro Domain (Standard 1.0 s) – keine Request-Fluten.
4. Weiterleitungen werden **manuell** gefolgt: jeder Location-Header läuft
   erneut durch ``ssrf.check_redirect`` (Rebind-/Umleitungs-Schutz).
5. Zeit- und Größenlimits (MAX_RESPONSE_BYTES, Timeouts) – kein
   unbegrenztes Laden.

ZENJI umgeht **nicht**: Logins, Captchas, Paywalls, Zugriffsbeschränkungen.
Es sendet einen ehrlichen User-Agent und behandelt 401/403/429 als
„nicht zugreifbar“ mit verständlicher Meldung.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.core.exceptions import WebFetchError, WebSecurityError
from app.core.logging import get_logger
from app.web_intelligence import ssrf

log = get_logger("browser_engine")

#: Mindestabstand zwischen zwei Abrufen derselben Domain (Höflichkeit).
PER_HOST_DELAY_S = 1.0
#: robots.txt Cache-Dauer.
ROBOTS_TTL_S = 3600.0
#: Inhaltstypen, die als Webseite akzeptiert werden.
ACCEPTABLE_CONTENT_TYPES = ("text/html", "application/xhtml", "text/plain", "application/xml")
#: Statuscodes, die als „nicht umgehbar“ gelten (keine Umgehungsversuche!).
NO_BYPASS_STATUSES = {401, 402, 403, 429}
_REDIRECT_CODES = {301, 302, 303, 307, 308}


class _AccessDenied(WebFetchError):
    """Interner Marker: Zugriff verweigert – **kein** Fallback-Versuch erlaubt.

    Erbt von ``WebFetchError`` (gleicher Code/HTTP-Status nach außen), stoppt
    aber die Playwright-Fallback-Kette: 401/402/403/429 werden niemals durch
    einen zweiten Versuch „umgangen“.
    """


@dataclass(slots=True)
class FetchResult:
    """Ergebnis eines Abrufs (HTML begrenzt, Metadaten extrahiert)."""

    url: str
    final_url: str
    status: int
    content_type: str
    html: str
    title: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    via_playwright: bool = False
    truncated: bool = False


class _RobotsEntry:
    """robots.txt einer Origin (geparst, mit Zeitstempel)."""

    __slots__ = ("parser", "fetched_at", "exists")

    def __init__(self, parser: RobotFileParser | None, exists: bool) -> None:
        self.parser = parser
        self.fetched_at = time.monotonic()
        self.exists = exists

    def allows(self, url: str, useragent: str) -> bool:
        if self.parser is None:
            return True  # keine robots.txt → alles erlaubt (RFC-Verhalten bei 404)
        return self.parser.can_fetch(useragent, url)


class BrowserEngine:
    """Sicherer HTTP-Abruf mit Redirect-Validierung, robots.txt und Limits."""

    name = "browser"

    def __init__(
        self,
        *,
        timeout: float = ssrf.DEFAULT_TIMEOUT_S,
        max_bytes: int = ssrf.MAX_RESPONSE_BYTES,
        transport: httpx.AsyncTransport | None = None,
        robots: bool = True,
        per_host_delay: float = PER_HOST_DELAY_S,
        playwright_fallback: bool = True,
        resolver=None,
    ) -> None:
        self._timeout = timeout
        self._max_bytes = max_bytes
        self._transport = transport
        self._robots_enabled = robots
        self._per_host_delay = per_host_delay
        self._playwright_fallback = playwright_fallback
        self._resolver = resolver or ssrf.resolve_host
        self._robots_cache: dict[str, _RobotsEntry] = {}
        self._last_fetch: dict[str, float] = {}
        # Betriebsstatistik (für /api/web/status):
        self.stats = {"fetches": 0, "failures": 0, "last_fetch_url": "", "last_fetch_at": None}

    # --- Öffentliche API --------------------------------------------------------------

    async def fetch(self, url: str, *, timeout: float | None = None) -> FetchResult:
        """Lädt eine URL **sicher** und liefert HTML + Metadaten.

        Jeder Redirect-Hop wird neu validiert.  Blockierte Ziele (SSRF,
        robots.txt) enden in ``WebSecurityError``, Netzwerkprobleme in
        ``WebFetchError`` mit verständlicher Meldung.
        """
        try:
            checked = ssrf.check_url(url, resolver=self._resolver)
        except WebSecurityError:
            self.stats["failures"] += 1
            raise
        self.stats["fetches"] += 1

        await self._respect_robots(checked.url)
        await self._politeness_delay(checked.hostname)

        effective_timeout = timeout or self._timeout
        current_url = checked.url
        try:
            result = await self._fetch_with_httpx(current_url, effective_timeout)
            self._record_success(result)
            return result
        except WebSecurityError:
            self.stats["failures"] += 1
            raise
        except _AccessDenied:
            # Zugriff verweigert → **niemals** einen Umgehungsversuch starten.
            self.stats["failures"] += 1
            raise
        except WebFetchError as exc:
            self.stats["failures"] += 1
            # Optionaler Playwright-Fallback (falls installiert):
            if self._playwright_fallback:
                result = await self._try_playwright(current_url, effective_timeout)
                if result is not None:
                    self._record_success(result)
                    return result
            raise
        except httpx.HTTPError as exc:
            self.stats["failures"] += 1
            raise WebFetchError(
                f"Website konnte nicht geladen werden: {type(exc).__name__}."
            ) from exc

    # --- httpx-Pfad ------------------------------------------------------------------

    async def _fetch_with_httpx(self, url: str, timeout: float) -> FetchResult:
        """Abruf mit **manueller** Redirect-Behandlung (Validierung pro Hop)."""
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=ssrf.CONNECT_TIMEOUT_S),
            transport=self._transport,
            follow_redirects=False,
            headers={"User-Agent": ssrf.USER_AGENT, "Accept-Language": "de,en"},
        ) as client:
            hops = 0
            while True:
                # Validierung pro Hop (DNS + Policy) – gegen Rebinding/Redirects:
                ssrf.check_url(url, resolver=self._resolver)
                response = await client.get(url)
                if response.status_code in _REDIRECT_CODES:
                    location = response.headers.get("location")
                    if hops >= ssrf.MAX_REDIRECTS:
                        raise WebFetchError(
                            f"Zu viele Weiterleitungen (> {ssrf.MAX_REDIRECTS}) – Abbruch."
                        )
                    url = ssrf.check_redirect(url, location, resolver=self._resolver)
                    hops += 1
                    continue
                return await self._build_result(response, requested_url=url)

    async def _build_result(self, response: httpx.Response, *, requested_url: str) -> FetchResult:
        status = response.status_code
        content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
        final_url = str(response.request.url)

        if status in NO_BYPASS_STATUSES:
            raise _AccessDenied(
                f"Zugriff verweigert (HTTP {status}) – ZENJI umgeht keine "
                "Zugriffsbeschränkungen, Logins oder Paywalls."
            )
        if status >= 400:
            raise WebFetchError(f"Website antwortete mit HTTP {status}.")

        if content_type and not any(
            content_type.startswith(prefix) for prefix in ACCEPTABLE_CONTENT_TYPES
        ):
            raise WebFetchError(
                f"Nicht unterstützter Inhaltstyp '{content_type}' (erwartet HTML/Text)."
            )

        # Größenlimit beim Lesen durchsetzen (Streaming):
        chunks: list[bytes] = []
        received = 0
        truncated = False
        async for chunk in response.aiter_bytes():
            chunks.append(chunk)
            received += len(chunk)
            if received >= self._max_bytes:
                truncated = True
                await response.aclose()
                break
        raw = b"".join(chunks)[: self._max_bytes]
        try:
            html = raw.decode(response.encoding or "utf-8", errors="replace")
        except LookupError:  # unbekanntes Encoding
            html = raw.decode("utf-8", errors="replace")

        result = FetchResult(
            url=requested_url,
            final_url=final_url,
            status=status,
            content_type=content_type or "text/html",
            html=html,
            truncated=truncated,
        )
        self._extract_page_metadata(result, html)
        return result

    @staticmethod
    def _extract_page_metadata(result: FetchResult, html: str) -> None:
        """Title/Canonical/Meta-Description aus dem HTML ziehen (bs4, robust)."""
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html[:200_000], "html.parser")
            if soup.title and soup.title.string:
                result.title = " ".join(soup.title.string.split())[:300]
            meta: dict[str, str] = {}
            canonical_tag = soup.find("link", rel=lambda v: bool(v) and "canonical" in (v or []))
            if canonical_tag and canonical_tag.get("href"):
                meta["canonical"] = canonical_tag["href"]
            for name_attr in ("description", "author", "article:author", "og:title", "og:description"):
                tag = (
                    soup.find("meta", attrs={"name": name_attr})
                    or soup.find("meta", attrs={"property": name_attr})
                )
                if tag and tag.get("content"):
                    meta[name_attr] = tag["content"][:500]
            result.metadata = meta
            if not result.title and meta.get("og:title"):
                result.title = meta["og:title"]
        except Exception as exc:  # noqa: BLE001 – Metadaten dürfen nie den Abruf sprengen
            log.debug("Metadaten-Extraktion fehlgeschlagen: %s", exc)

    # --- robots.txt & Höflichkeit -----------------------------------------------------

    async def _respect_robots(self, url: str) -> None:
        if not self._robots_enabled:
            return
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        entry = self._robots_cache.get(origin)
        if entry is None or time.monotonic() - entry.fetched_at > ROBOTS_TTL_S:
            entry = await self._fetch_robots(origin)
            self._robots_cache[origin] = entry
        if not entry.allows(url, ssrf.USER_AGENT):
            raise WebSecurityError(
                f"robots.txt der Domain '{parts.hostname}' erlaubt diesen Abruf "
                "nicht – ZENJI respektiert das."
            )

    async def _fetch_robots(self, origin: str) -> _RobotsEntry:
        """robots.txt laden/parieren. Fail-open bei Netzwerkproblemen (dokumentiert)."""
        parser = RobotFileParser()
        try:
            async with httpx.AsyncClient(
                timeout=10.0, transport=self._transport, follow_redirects=False,
                headers={"User-Agent": ssrf.USER_AGENT},
            ) as client:
                response = await client.get(f"{origin}/robots.txt")
            if response.status_code == 200:
                text = response.text[:100_000]
                parser.parse(text.splitlines())
                return _RobotsEntry(parser, exists=True)
            if response.status_code == 404:
                return _RobotsEntry(None, exists=False)
            # 5xx: robots.txt nicht auswertbar → konservativ alles erlauben,
            # aber protokolliert (Fail-open, dokumentiert in WEB_SECURITY.md).
            log.warning("robots.txt HTTP %s für %s – Fail-open.", response.status_code, origin)
            return _RobotsEntry(None, exists=False)
        except httpx.HTTPError as exc:
            log.warning("robots.txt nicht erreichbar für %s (%s) – Fail-open.", origin, exc)
            return _RobotsEntry(None, exists=False)

    async def _politeness_delay(self, hostname: str) -> None:
        """Mindestabstand pro Domain (keine Request-Fluten)."""
        if self._per_host_delay <= 0:
            return
        now = time.monotonic()
        last = self._last_fetch.get(hostname)
        if last is not None:
            elapsed = now - last
            if elapsed < self._per_host_delay:
                await asyncio.sleep(self._per_host_delay - elapsed)
        self._last_fetch[hostname] = time.monotonic()

    def _record_success(self, result: FetchResult) -> None:
        self.stats["last_fetch_url"] = result.final_url
        self.stats["last_fetch_at"] = result.fetched_at.isoformat()

    # --- Playwright-Fallback (optional) -------------------------------------------------

    async def _try_playwright(self, url: str, timeout: float) -> FetchResult | None:
        """JavaScript-lastige Seiten: Playwright, **nur wenn installiert**.

        Rückgabe None = Playwright nicht verfügbar → Aufrufer behält den
        httpx-Fehler.  Das Ziel wurde bereits per SSRF-Policy geprüft; die
        erreichte URL wird nach dem Laden **erneut** validiert.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return None
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                try:
                    page = await browser.new_page(user_agent=ssrf.USER_AGENT)
                    await page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
                    final_url = page.url
                    ssrf.check_url(final_url, resolver=self._resolver)  # Re-Validierung
                    html = await page.content()
                finally:
                    await browser.close()
        except WebSecurityError:
            raise
        except Exception as exc:  # noqa: BLE001 – Fallback darf nie hart scheitern
            log.debug("Playwright-Fallback fehlgeschlagen: %s", exc)
            return None
        result = FetchResult(
            url=url, final_url=final_url, status=200, content_type="text/html",
            html=html[: self._max_bytes], via_playwright=True,
            truncated=len(html) > self._max_bytes,
        )
        self._extract_page_metadata(result, result.html)
        return result

    # --- Status (Control Center) ---------------------------------------------------------

    def status(self) -> dict[str, object]:
        """Ehrliche Betriebszustände: httpx immer aktiv, Playwright optional."""
        try:
            import playwright  # noqa: F401

            playwright_available = True
        except ImportError:
            playwright_available = False
        return {
            "httpx": {"available": True, "detail": "httpx-Browserpfad aktiv."},
            "playwright": {
                "available": playwright_available,
                "detail": (
                    "Playwright installiert (Fallback für JS-Seiten)."
                    if playwright_available
                    else "Playwright nicht installiert – JavaScript-lastige Seiten "
                    "können nur teilweise gelesen werden (optional: pip install playwright)."
                ),
            },
            "robots_respected": self._robots_enabled,
            "per_host_delay_s": self._per_host_delay,
            "max_bytes": self._max_bytes,
            "timeout_s": self._timeout,
            **self.stats,
        }


__all__ = ["BrowserEngine", "FetchResult", "NO_BYPASS_STATUSES", "PER_HOST_DELAY_S"]
