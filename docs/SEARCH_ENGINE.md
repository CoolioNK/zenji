# Search Engine (Suchschicht, v0.5.0)

Die Suchschicht fragt Websuchanbieter ab und liefert **normalisierte,
deduplizierte** Treffer – unabhängig davon, welcher Anbieter antwortet.

## 1. Architektur (`app/web_intelligence/search_engine.py`)

```
SearchEngine (Fassade)
 ├── SearXNGProvider   lokale/metasearch-Instanz, JSON-API, kein Schlüssel
 └── BraveProvider     Brave Search API, braucht API-Schlüssel
```

- **SearchProvider-Protocol** (`name`, `search()`, `status()`): eigene
  Provider sind registrierbar (`SearchEngine({name: provider})`).
- **Normalisierung** (`_normalize`): bereinigte Felder, `domain_of`,
  `canonical_url` (Tracking-Parameter raus), `parse_published`
  (robustes Datumsparsing; `None` erlaubt).
- **Dedupe/Merge** (`merge_results`): gleiche Kanonische URL → erster
  Treffer gewinnt, Reihenfolge = Anbieterreihenfolge + Rang.

## 2. SearXNG (Default)

- Endpoint: `{searxng_url}/search?q=…&format=json&language=…`
- Benötigt eine SearXNG-Instanz mit freigegebener JSON-API
  (`settings.yml`: `formats: [html, json]`), typischerweise lokal per
  Docker (`localhost:8888`).
- Läuft die Instanz nicht, meldet `status()` ehrlich
  `available: false` mit Detail – es gibt keinen Fake-Zustand.

## 3. Brave

- Endpoint `https://api.search.brave.com/res/v1/web/search` mit
  `X-Subscription-Token`.
- Schlüsselverwaltung über die Einstellungsgruppe `web_intelligence`
  (`brave_api_key`). Der Schlüssel wird nie in API-Antworten,
  Logs oder `status()`-Ausgaben preisgegeben.

## 4. SearchResult (normalisiert)

```json
{
  "title": "…", "url": "https://…", "domain": "example.com",
  "snippet": "…", "provider": "searxng", "rank": 1,
  "published_at": "2026-11-02T00:00:00+00:00"
}
```

## 5. Fehlerverhalten

- `SearchProviderError` (ehrliche Meldung mit Ursache) bei Ausfall –
  die Recherche-Engine stuft das als `search_failed`-Ereignis ein und
  läuft kontrolliert weiter (Status `partial`/`failed`).
- Timeouts begrenzen jede Anfrage; Suchanfragen landen (mit Ergebnisanzahl)
  in `search_queries` – Nachvollziehbarkeit auch bei Fehlern.
