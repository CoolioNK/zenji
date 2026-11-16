# ZENJI – Entwicklungsbericht Phase 3: Web Intelligence Engine

Datum: 16. November 2026 · Version: **0.5.0** · Umsetzung nach Master-Prompt
„Phase 3 – Web Intelligence Engine" (9 Komponenten, DB, API, Chat-Integration,
Frontend, Tests offline, Doku).

## 1. Zielsetzung

ZENJI soll **eigenständig das Internet recherchieren können**: Suchen,
Seiten abrufen, Inhalte extrahieren, Quellen bewerten, Widersprüche finden
und Antworten mit **nachvollziehbaren Belegen** versehen. Alles mit den
bereits etablierten Prinzipien: fail-soft, ehrliche Meldungen, volle
Nutzerkontrolle, keine Fake-Funktionen, keine Model-Abhängigkeit –
Recherche ist ein **System-Feature**, kein Modell-Feature.

## 2. Implementierung

### 2.1 Neun Komponenten (`backend/app/web_intelligence/`)

| Komponente | Aufgabe | Umsetzung |
|---|---|---|
| `ssrf.py` | URL-/IP-Schutz | Nur http(s); Private/Loopback/Link-local-Ranges blockiert; IP-Literale direkt geprüft; `check_redirect` für jeden Redirect-Hop |
| `search_engine.py` | Suchschicht | `SearchProvider`-Protocol; SearXNG (JSON-API) + Brave (API-Schlüssel); Normalisierung, Canonical-URL, Datumsparsing, `merge_results`-Dedupe |
| `browser_engine.py` | Abrufschicht | httpx (+ optional Playwright-Fallback); robots.txt pro Host gecacht + respektiert; Host-Pause (1 s), Timeouts (20 s), Redirect-Limit (5); `FetchResult` mit Blockierungsgrund |
| `content_extractor.py` | HTML → Text | trafilatura bevorzugt, BeautifulSoup-Heuristik als Fallback; Titel/Autor/Datum/Canonical/Überschriften/Tabellen |
| `source_manager.py` | Quellen | Registrierung mit Canonical-Dedupe; Snapshot-Upsert nur bei neuem SHA-256-Inhaltshash |
| `source_analysis.py` | Bewertung | Quelltyp (7 Typen + Grund), Frische, Transparenz, Relevanz (0–1), Zahlen-Claims + Widerspruchserkennung |
| `citation_engine.py` | Belege | Marker-Whitelist aus Report-`refs`; erfundene `[n]` werden entfernt, Text bleibt vollständig; Warnungen |
| `research_cache.py` | Cache | Such- und Abruf-Cache mit TTL (Default 1800 s), `clear`/`purge_expired`/`stats` |
| `research_planner.py` | Planung | Bedarfserkennung (Aktualität/Frische/Vergleich/Aufforderung), `ResearchPlan` mit Modus-Limits |

### 2.2 Orchestrator + Fassade

- `research_engine.py`: `run()` – Plan → Session → Such-/Abrufschleife mit
  Cache → Registrierung/Extraktion/Bewertung → Fakten mit Markern →
  Widersprüche/Lücken → kontrollierter Abschluss (`done`/`partial`/
  `cancelled`/`failed`); Zeitlimit und Abort-Event werden respektiert.
  Report-Dict mit `session_id`, `facts`, `sources`, `refs`, `stats`.
  `context_block()` liefert den Datenblock für den Kontext (mit Marker-Belegen).
- `app/services/web_intelligence_service.py`: Fassade (Konfiguration,
  Suche, Recherche, Status, Verwaltung). Liest/schreibt die
  Einstellungsgruppe `web_intelligence`; `brave_api_key` wird **nie**
  zurückgegeben.

### 2.3 Datenbank (Migration 4 → 5)

Sieben neue Tabellen: `research_sessions`, `search_queries`,
`search_results`, `sources`, `source_snapshots`, `citations`,
`research_cache` (Check-Constraints für Modus/Status). `LATEST_VERSION=5`,
Migration als reiner Version-Bump – Seeds (9 Regeln/8 System, 5 Profile)
bleiben unverändert. Web-Repository mit Canonical-Dedupe, Snapshot-Upsert,
`enforce_limits` und TTL-Aufräumung.

### 2.4 Chat-Integration

- **ZenjiCore** (`prepare_turn(..., research_override, research_progress,
  research_abort_event)`): Modus normalisieren → Bedarf prüfen (nur auto) →
  Recherche mit Live-Callback → Report + Kontextblock. Fail-soft: fehlt die
  Engine oder scheitert die Recherche, antwortet ZENJI ohne Webbelege.
  `context_preview` recherchiert **nie live** (`research_override="off"`,
  nur `research_planned`-Anzeige).
- **ContextEngine**: `research`-Parameter; Datenblock zwischen Erinnerungen
  und Verlauf, ummantelt mit `[INHALT_BEGINN]/[INHALT_ENDE]`; Budget-Floor
  `MIN_RESEARCH_CHARS=1200` (kürzen bis zum Floor, sonst Abschnitt ersatzlos
  streichen – kein Mini-Fragment); `ContextPlan.research_tokens`.
- **ChatService**: Queue-Task-Muster für den Stream – Recherche-Callback
  pusht echte `research`-SSE-Events **live** in die Queue; `done`-Payload
  mit `research`-Zusammenfassung (session_id, status, mode, queries,
  sources, Widersprüche, `citations_corrected`, warnings).
  Citation-Validierung direkt vor Persistenz der Antwort.
- **SQLite-Lock-Fix**: Chat-Flow in getrennte Transaktionen (Nutzernachricht
  committen **vor** der Recherche; Kontext-Lesen + LLM-Aufruf + Antwort-
  Persistenz jeweils eigene Sessions) – verhindert `database is locked`
  gegen die eigenen Sessions der Recherche-Engine.
- **ChatRequest**: `research: str = "auto"` mit Validierung
  (auto/off/quick/standard/deep).

### 2.5 API (Phase 3)

`/api/web` (search, settings GET/PATCH ohne Schlüssel-Rückgabe, status,
cache DELETE), `/api/research` (POST, POST /stream als SSE mit Abort,
GET-Liste, GET-Detail, DELETE), `/api/sources` (Liste mit Domain/Typ-Filter,
Detail, Snapshot, DELETE). Zusätzlich `research_planned`/`research_tokens`
im `context-preview`.

### 2.6 Frontend

- **Datenschicht** (`types/index.ts`, `services/api.ts`, `hooks/useChat.ts`):
  Web-/Recherche-/Quellen-Typen, API-Methoden, `openChatStream(..., research)`,
  `researchEvents` (live) + `researchSummary` (aus done).
- **Composer**: zweites Auswahlfeld „Web: Auto/Aus/Schnell/Standard/Tief".
- **ChatArea**: Research-Panel mit Live-Schritten (letzte 5) und
  Quellen-Chips mit Markern nach Abschluss.
- **ChatPage**: researchMode-State, Verkabelung der neuen Props.
- **Control Center → Tab „Web"** (`WebIntelligenceTab.tsx`): ehrlicher
  Status (Suchanbieter/httpx/Playwright/robots/Cache/Speicher),
  Einstellungen (Provider, SearXNG-URL, Sprache, Cache-TTL, Brave-Schlüssel
  nur als „neu setzen"-Feld, nie anzeigbar), Websuche mit Ergebnisliste,
  Recherche-Verlauf (löschen), Quellen (Domain-/Typ-Filter, Snapshot-
  Ansicht, löschen). Nur bestehende Design-Primitives, keine neue
  Icon-Abhängigkeit.

## 3. Tests (offline, ohne echtes Internet)

**396 Tests grün** (378 Bestand + 18 neue). Sämtliche Webpfade sind
gemockt: `FakeSearchProvider` (Fehler-Szenarien, Anfrage-Protokoll),
`httpx.MockTransport` für Seitenabrufe, resolver-injizierter Browser.
Neu: `test_web_security.py` (SSRF/robots/Geheimnisse),
`test_search_engine.py`, `test_research_planner.py`,
`test_research_engine.py` (Orchestrator, Events, Report, Cache),
`test_web_database.py` (Migration 5, Dedupe, Limits, TTL),
`test_api_web.py` (alle Endpunkte inkl. SSE-Ereigniskette, Chat mit
erzwungener Recherche + Zitatkorrektur, research=off, Preview ohne
Live-Recherche).

## 4. Live-Verifikation (echtes System)

- Backend v0.5.0 gestartet, echte DB auf `user_version=5`, alle 7 Tabellen
  vorhanden.
- `GET /api/web/status` meldet ehrlich: SearXNG nicht erreichbar (mit
  Hinweis), httpx aktiv, Playwright nicht installiert.
- Chat mit `research=quick`: ehrliche Ereigniskette `planning → planned →
  searching → search_failed (SearXNG down) → comparing (0 Quellen) →
  failed → research_failed`, danach normale Antwort **ohne Webbelege**
  (fail-soft). Session bleibt als `failed` dokumentiert (Nachvollziehbarkeit).
- Chat mit `research=auto` bei Konzeptfrage: keine Recherche (Bedarf
  korrekt verneint), Antwort ohne research-Events.
- Test-Sessions danach aus der echten DB gelöscht (Nutzerkontrolle
  funktioniert auch live).

## 5. Architektur-Entscheidungen

1. **Recherche als System-Feature**: ZenjiCore entscheidet (Bedarf +
   Override), nicht das Modell. Der Kontextblock ist strikt Daten
   (`[INHALT_BEGINN]`), nie Anweisung – Injection über Webseiteninhalte
   läuft ins Leere.
2. **Beleg-Whitelist nach dem Generieren**: Das Modell sieht erlaubte
   Marker im Kontext; die CitationEngine entfernt nachträglich alles
   Erfundene. Doppelte Sicherheit statt blindem Vertrauen.
3. **Echte Ereignisse statt Lüge**: Jedes `research`-SSE-Event beschreibt
   einen ausgeführten Schritt. Nichts wird animiert, das nicht passiert.
4. **Quellen sind Sitzungsdaten**: Reports gehen nicht automatisch ins
   Gedächtnis; Löschen ist Nutzerentscheidung (Sessions, Quellen, Cache).
5. **Getrennte Transaktionen** im Chatflow – SQLite-Schreibkonflikte
   zwischen Chat-Persistenz und Recherche-Engine strukturell ausgeschlossen.

## 6. Grenzen (bewusst, nicht versteckt)

- Ohne laufenden SearXNG-Docker (oder Brave-Schlüssel) findet keine
  Recherche statt – der Status sagt es ehrlich, der Chat läuft weiter.
- Playwright fehlt: JavaScript-lastige Seiten bleiben evtl. leer
  (httpx-Text oder blockiert), das steht im Report.
- Quote/Robots-Blockaden werden akzeptiert (`blocked`), nie umgangen.
- Marker-Prüfung prüft Existenz, nicht inhaltliche Korrektheit des Satzes –
  dafür stehen Quellbewertung, Transparenz und Widerspruchsanalyse.
- Login-/Paywall-Seiten werden nicht gelesen (bewusst kein Umgehungspfad).

## 7. Empfehlungen für Phase 4+

- SearXNG-Docker in `scripts/` verankern (`scripts/searxng` wird im
  Statusdetail erwähnt; Docker ist installiert).
- Playwright optional installieren für JS-lastige Seiten.
- Recherche-„Merken"-Aktion: bewusste Übernahme von Quellen ins Gedächtnis
  (aktuell bewusst ausgenommen).
- Optional: zweiter SearXNG-Fallback-Host, E2E-Playwright-Tests fürs UI.

## 8. Fazit

Phase 3 liefert eine vollständig funktionsfähige, ehrliche
Web-Intelligence: 9 Komponenten, 7 Tabellen, 15 neue API-Endpunkte,
Chat-Integration mit Live-Fortschritt und Belegvalidierung, vollständiges
Control-Center-Tab – offline getestet (396 grün) und live verifiziert.
ZENJI recherchiert jetzt selbst, bewertet Quellen und legt offen, woher
sein Wissen kommt.
