# Source Management (Quellen & Analyse, v0.5.0)

Jede besuchte Seite wird als **Quelle registriert** – mit Kanonisierung,
Inhaltssnapshot und automatischer Bewertung. Der Nutzer sieht jede Quelle
und kann sie löschen.

## 1. Content Extractor (`content_extractor.py`)

- HTML → Haupttext: **trafilatura** (bevorzugt), Fallback
  **BeautifulSoup**-Heuristik (`extractor`-Feld zeigt, was gelaufen ist).
- Metadaten: Titel, Autor, Veröffentlichungsdatum, Canonical-URL,
  Überschriften, Tabellen; `context_text(max_chars)` liefert den
  kompakten Text für die Analyse.
- Leere/JS-lastige Seiten: aus Playwright-Fallback oder ehrlich leer
  (Quelle wird `status: blocked`/`leer` vermerkt, nicht erfunden).

## 2. Source Manager (`source_manager.py`)

- `register_fetch(...)`: registriert oder aktualisiert eine Quelle.
  **Canonical-Dedupe:** identische kanonische URL wird wiederverwendet
  (keine Doppelquellen), Snapshot-Upsert nur bei neuem `content_hash`
  (SHA-256) – gleiche Inhalte werden nicht doppelt gespeichert.
- Snapshot = lokale Kopie des Extraktionszeitpunkts (Grundlage für
  nachvollziehbare Belege). `snapshot_text`, `list`, `get`, `delete`,
  `count`.

## 3. Source Analysis (`source_analysis.py`)

Bewertet jede Quelle automatisch:

| Feld | Bedeutung |
|---|---|
| `source_type` | `offiziell` \| `wissenschaftlich` \| `fachquelle` \| `nachrichten` \| `community` \| `meinung` \| `unbekannt` (Domänen-Heuristik + Inhaltssignale) |
| `type_reason` | ehrlicher Grund der Einordnung |
| `freshness` / `age_days` | frisch / aktuell / veraltet / unbekannt |
| `transparency` | Autor/Datum/Impressum-Spuren vorhanden? |
| `relevance` | 0–1 (Themen-Übereinstimmung mit der Frage) |
| `notes` | Auffälligkeiten (z. B. „kein Datum“, „Meinungsstile“) |

**Konflikterkennung:** `extract_claims` zieht Aussagen mit Zahlen
(`NumericClaim`), `detect_conflicts` vergleicht Zahlen-Shapes über Quellen –
widersprüchliche Angaben erscheinen im Report unter `contradictions`
(inkl. Markern), damit die Antwort sie offenlegen kann.

## 4. Tabellen (Nutzerkontrolle)

| Tabelle | Inhalt |
|---|---|
| `sources` | URL (original/canonical), Domain, Titel, Autor, Datum, Hash, HTTP-Status, Typ, Zeichenzahl |
| `source_snapshots` | Inhaltstext, Hash, Extractor, Zeichenzahl, Zeitpunkt |
| `citations` | Belegaussagen je Recherche-Session (statement, marker, source_id) |

Löschen über `DELETE /api/sources/{id}` (Quelle + Snapshot) bzw.
`DELETE /api/research/{id}` (Session + Zitate). Der Repo-Layer erzwingt
`enforce_limits` (Snapshots pro Quelle, Gesamtzahl) und TTL-Aufräumung –
Speicher wächst nicht unbegrenzt.
