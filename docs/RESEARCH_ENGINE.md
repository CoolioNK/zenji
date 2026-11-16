# Research Engine (Recherche-Orchestrierung, v0.5.0)

Die Recherche-Engine plant, führt durch und persistiert eine vollständige
Internet-Recherche – mit echten Fortschrittsereignissen, Quellenbewertung
und nachvollziehbarem Report.

## 1. Research Planner (`research_planner.py`)

- `normalize_mode(mode)`: `auto→""`, `off`, `quick|standard|deep`
  (Unbekanntes → `ValidationError`).
- `needs_research(text)`: Bedarfserkennung – Aktualitätssignale
  („aktuell“, „neueste“, „heute“, Jahreszahlen …), Frische-Themen
  (Nachrichten, Versionen, Preise, Sport, Wetter …), Vergleiche und
  ausdrückliche Aufforderungen („recherchiere“, „such im Netz“).
- `build_plan(text, mode, force)` → `ResearchPlan`: bereinigte Frage,
  Thema, Suchvarianten (Synonyme/Anführungszeichen), Modus + `ResearchLimits`
  (Suchanfragen, Quellen, Zeichen, Folgerunden, Zeitlimit) und ehrlicher
  Grund (`reason`), warum recherchiert wird.

## 2. Research Engine (`research_engine.py`)

Ablauf von `run(question, mode, force, progress, abort_event)`:

```
Plan bauen → Session-Zeile anlegen (status=running)
  pro Planfrage:
    Cache prüfen (ResearchCache) → sonst Suche (SearchEngine)
    pro Treffer (Reihenfolge, Dedupe):
      SSRF + robots prüfen → Abruf (BrowserEngine)
      Inhalt extrahieren (trafilatura/BS4)
      Quelle registrieren + Snapshot speichern (SourceManager)
      Quelle bewerten (SourceAnalysisEngine: Typ, Frische,
        Transparenz, Relevanz)
    Fakten mit Marker [n] aus Bewertungskontext
    Widersprüche: Zahlen-Shapes über Quellen vergleichen
    ggf. Folgerunde (nur standard/deep, wenn Lücken bleiben)
  Abschluss: Status done|partial|cancelled|failed, Report persistieren
  Rückgabe: Report-Dict + context_block(...) (Datenblock für den Kontext)
```

- **Abbruch/Zeitlimit** enden kontrolliert (`cancelled`/`partial`) – es wird
  nie unbegrenzt recherchiert.
- **Live-Events** (Progress-Callback → SSE `research`): `planned`,
  `searching`, `found`, `fetching`, `fetched`, `blocked`, `search_failed`,
  `comparing`, `done`. Jedes Event beschreibt einen realen Schritt.

## 3. Report-Struktur

```json
{
  "session_id": "uuid", "question": "…", "mode": "quick", "status": "done",
  "topic": "…", "queries": ["…"],
  "facts":   [{ "text": "…", "marker": 1, "source_id": "…", "source_type": "offiziell" }],
  "contradictions": [{ "topic": "…", "statements": [ { "marker": 1, "text": "…", "numbers": [3.14] } ] }],
  "gaps": ["…"],
  "sources": [ { "marker": 1, "id": "…", "title": "…", "url": "…", "domain": "…",
                 "source_type": "offiziell", "status": "ok", "freshness": "frisch",
                 "transparency": "…", "relevance": 0.82, "notes": [] } ],
  "refs": [ { "source_id": "…", "title": "…", "url": "…", "domain": "…", "source_type": "…" } ],
  "stats": { "queries": 1, "cache_hits": 0, "fetches": 1, "errors": [], … }
}
```

`refs` ist die **whitelist für Marker** im Chat: Nur diese Quellen dürfen
belegt werden (docs/CITATION_SYSTEM.md).

## 4. Kontextblock (`context_block`)

Kompakter, rein informativer Text: Frage, QUELLEN (mit Marker), FAKTEN mit
Beleg-Markern, Widersprüche/Lücken. Begrenzt auf Standardmaß (max. Zeichen),
damit das Token-Budget des Chats gesund bleibt. Die ContextEngine ummantelt
ihn als `[INHALT_BEGINN]/[INHALT_ENDE]`-Datenblock (docs/CONTEXT_ENGINE.md).

## 5. Persistenz

Jeder Durchlauf landet in `research_sessions` (Plan-JSON, Report-JSON,
Status, Quellenzahl, Dauer), Suchanfragen in `search_queries`, Belegaussagen
in `citations` – Löschbar über `DELETE /api/research/{id}`.
