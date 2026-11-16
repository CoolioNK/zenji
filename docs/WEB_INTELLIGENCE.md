# Web Intelligence Engine (Phase 3, v0.5.0)

ZENJI kann seit v0.5.0 **eigenständig das Internet recherchieren**: Suchen,
Seiten abrufen (Regeln und Höflichkeit wahren), Inhalte extrahieren, Quellen
bewerten, Widersprüche erkennen und Antworten mit **nachvollziehbaren
Belegen** ([1], [2] …) versehen.

**Leitprinzip:** Recherche ist ein System-Feature, kein Modell-Feature. ZENJI
entscheidet, wann recherchiert wird, welche Quellen gelten und welche Belege
in die Antwort dürfen – erfundene Marker werden entfernt.

## 1. Bausteine (`app/web_intelligence/`)

| Modul | Aufgabe | Doc |
|---|---|---|
| `search_engine.py` | Suche (SearXNG/Brave), Normalisierung, Dedupe | docs/SEARCH_ENGINE.md |
| `browser_engine.py` | Abrufe: SSRF, robots.txt, Host-Pause, Timeouts | docs/BROWSER_ENGINE.md |
| `ssrf.py` | URL-Validierung, IP-Schutz, Redirect-Prüfung | docs/WEB_SECURITY.md |
| `content_extractor.py` | HTML → Text (trafilatura, Fallback BeautifulSoup) | docs/RESEARCH_ENGINE.md |
| `source_manager.py` | Quellen registrieren, Snapshots, Dedupe | docs/SOURCE_MANAGEMENT.md |
| `source_analysis.py` | Quelltyp, Frische, Transparenz, Relevanz, Konflikte | docs/SOURCE_MANAGEMENT.md |
| `citation_engine.py` | Marker-Prüfung, erfundene Belege entfernen | docs/CITATION_SYSTEM.md |
| `research_cache.py` | Such-/Abruf-Cache mit TTL | docs/WEB_SECURITY.md |
| `research_planner.py` | Bedarfserkennung, Pläne, Limits je Modus | docs/RESEARCH_ENGINE.md |
| `research_engine.py` | Orchestrator: Plan → Suche → Abruf → Report | docs/RESEARCH_ENGINE.md |

Fassade nach außen: `app/services/web_intelligence_service.py`
(`WebIntelligenceService`) – Konfiguration, Suche, Recherche, Status,
Verwaltung. Eine Instanz liegt auf `app.state.web_intelligence` und wird an
`ZenjiCore` als `web_engine` übergeben.

## 2. Recherche-Modi

Der Nutzer steuert pro Nachricht (Chat-Feld „Web: …“) oder über
`research` im Chat-Request:

| Modus | Bedeutung | Limits (Suchanfragen / Quellen / Zeit) |
|---|---|---|
| `auto` (Default) | Bedarfserkennung des Planners – nur bei Aktualitäts-/Frische-/Vergleichssignalen | – |
| `off` | Nie recherchieren (auch im Kontext-Preview erzwungen) | – |
| `quick` | 1 Anfrage · max. 3 Quellen · max. 12.000 Zeichen · 20 s | 0 Folgerunden |
| `standard` | 3 Anfragen · max. 6 Quellen · 40.000 Zeichen · 60 s | 1 Folgerunde |
| `deep` | 5 Anfragen · max. 10 Quellen · 90.000 Zeichen · 120 s | 2 Folgerunden |

## 3. Datenfluss (Chat mit Recherche)

```
Nutzer („Was ist die neueste Python-Version?“)
  1. ChatService persistiert Nutzernachricht (eigene Transaktion, commit)
  2. ZenjiCore.prepare_turn:
     a. normalize_mode(research_override)   (auto/off/quick|standard|deep)
     b. Bedarfserkennung (nur bei auto)     (ResearchPlanner.needs_research)
     c. ResearchEngine.run(...)             → Live-Events „research“ (SSE)
     d. Report persistieren                 (research_sessions + Zitate)
     e. context_block(report)               → Datenblock für den Kontext
  3. ContextEngine bettet den Block zwischen Erinnerungen und Verlauf ein
     ([INHALT_BEGINN]/[INHALT_ENDE], Budget-Floor 1200 Zeichen)
  4. LLM-Antwort streamt (deltas)
  5. ChatService validiert Marker            (CitationEngine.validate:
     erfundene [n] fliegen raus, Warnungen bleiben sichtbar)
  6. done-Event enthält `research`-Zusammenfassung
     (session_id, status, mode, queries, sources, Widersprüche,
      korrigierte Marker, Warnungen)
```

Fehlstrategie: Fehlt die Engine, scheitert eine Suche oder ist das Netz
nicht erreichbar, läuft der Chat **ohne Webbelege** weiter. Ein
`failed`-Report bleibt dokumentiert (Historie), liefert aber keinen
Kontextblock. Nie wird ein erfindungsreicher „Fortschritt“ gesendet: Jedes
`research`-Event beschreibt einen tatsächlich ausgeführten Schritt
(`planned`, `searching`, `found`, `fetching`, `fetched`, `blocked`,
`comparing`, `done`, `research_failed` …).

## 4. Konfiguration (Einstellungsgruppe `web_intelligence`)

| Schlüssel | Default | Beschreibung |
|---|---|---|
| `provider` | `searxng` | `searxng` \| `brave` |
| `searxng_url` | `http://localhost:8888` | SearXNG-Instanz (JSON-API) |
| `brave_api_key` | leer | Brave-API-Schlüssel; wird **nie** zurückgegeben |
| `language` | `de` | Bevorzugte Ergebnissprache |
| `cache_ttl_s` | `1800` | Cache-Gültigkeit (60–86400 s) |

Änderung über `PATCH /api/web/settings` oder Control Center → Tab „Web“.

## 5. API-Kurzübersicht (Details: docs/API.md)

- `POST /api/web/search` – einzelne Websuche
- `GET/PATCH /api/web/settings` – Einstellungen (ohne Schlüssel-Rückgabe)
- `GET /api/web/status` – ehrlicher Betriebszustand
- `DELETE /api/web/cache` – Cache leeren (Nutzerkontrolle)
- `POST /api/research` / `POST /api/research/stream` (SSE) – Recherche
- `GET /api/research` / `GET /api/research/{id}` / `DELETE …` – Historie
- `GET /api/sources` (+ Filter) / `/{id}` / `/{id}/snapshot` / `DELETE` – Quellen

## 6. Datenbank (Migration 4 → 5)

Sieben neue Tabellen (alle nutzerkontrolliert löschbar):
`research_sessions`, `search_queries`, `search_results`, `sources`,
`source_snapshots`, `citations`, `research_cache`. Details:
docs/STORAGE.md und docs/SOURCE_MANAGEMENT.md.
