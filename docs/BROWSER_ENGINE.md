# Browser Engine (Abrufschicht, v0.5.0)

Holt Seiteninhalte – **regelbewusst und defensiv**: robots.txt, SSRF-Schutz,
Host-Pause, Timeouts. Nutzt `httpx` als Default und optional **Playwright**
für JavaScript-lastige Seiten (Fallback im Content Extractor).

## 1. Architektur (`app/web_intelligence/browser_engine.py`)

```
BrowserEngine
 ├── URL-Prüfung         ssrf.check_url (+ check_redirect bei jedem Hop)
 ├── robots.txt          urllib.robotparser, gecacht je Host
 ├── Host-Pause          pro Host min. Abstand (per_host_delay, Default 1 s)
 ├── Timeout/Redirects   begrenzt (Default: 20 s / 5 Hops)
 ├── httpx.Client        transport + resolver injizierbar (Tests)
 └── status()            ehrliche Verfügbarkeitsinfo (httpx/Playwright)
```

- `fetch(url) -> FetchResult`: URL, Status, Headers, HTML, Fetchdauer,
  Robots-Entscheid. Zugriffsverweigerung (robots/4xx/5xx/SSRF) →
  `_AccessDenied` bzw. kontrollierte `FetchResult`-Ablehnung; die Engine
  dokumentiert den Grund (`blocked`-Event).
- **Redirect-Kette:** jeder Hop wird neu gegen SSRF geprüft – ein Redirect
  auf eine interne Adresse wird abgebrochen.
- **Playwright:** nur falls installiert und der httpx-Abruf leeren/JS-lastigen
  Inhalt liefert; sonst bleibt es bei httpx. Kein harter Zwang – der
  Betrieb funktioniert komplett ohne Playwright.

## 2. Ehrlicher Status (`GET /api/web/status` → `browser`)

```json
{
  "httpx":     { "available": true,  "detail": "…" },
  "playwright":{ "available": false, "detail": "nicht installiert – JS-Seiten evtl. leer" },
  "robots_respected": true,
  "per_host_delay_s": 1.0,
  "stats": { "fetches": 0, "blocked": 0, "robots_denied": 0, "by_host": {} }
}
```

## 3. Grenzen (bewusst)

- Kein Cookie-/Session-Management, keine Login-Seiten: ZENJI liest nur
  öffentliche Inhalte.
- Bilder/Styles werden nicht geladen; nur HTML-Text zählt.
- Paywall-/Robots-Blockaden werden akzeptiert und im Report vermerkt
  (`blocked`, Quelle mit `status: blocked`) – nicht umgangen.
