# Memory Engine (Phase 2)

Die Memory Engine ist ZENJIs **Langzeitgedächtnis**: strukturierte
Erinnerungen mit Typen, Quellen, Relevanz und Status. Grundprinzipien:
Nichts wird heimlich gespeichert, nicht jede Nachricht landet im
Gedächtnis, der Nutzer hat volle Einsicht- und Löschkontrolle, und
Widersprüche werden nachgefragt statt erraten.

## 1. Datenmodell

Tabelle `memories` (+ FTS-Index `memories_fts`):

| Feld | Typ | Bedeutung |
|---|---|---|
| `id` | str | UUID |
| `content` | str | Der Inhalt (max. 2000 Zeichen) |
| `content_hash` | str | SHA-256 des normalisierten Inhalts (Duplikatschlüssel, indiziert) |
| `category` | str | z. B. `identität`, `präferenz`, `projekt`, `allgemein` |
| `memory_type` | str | `conversation` / `long_term` / `preference` / `project` |
| `source` | str | `chat` (Merkwort im Chat) / `user` (UI/API) |
| `source_ref` | str \| null | Herkunftsbezug (z. B. Konversations-ID) |
| `relevance` | float 0–1 | Basisrelevanz (Nutzer/Engine) |
| `status` | str | `active` / `superseded` / `archived` |
| `supersedes_id` | str \| null | Vorgänger bei Veralten (Nachvollziehbarkeit) |
| `last_used_at` | datetime \| null | Wann im Kontext verwendet |

Datenschutz: Quelle und Bezug sind in **jeder** Erinnerung sichtbar
(API, UI); Löschen entfernt die Erinnerung **und** ihren FTS-Index-Eintrag.

## 2. Anlegen: Dedupe → Merge → Veralten → Konflikt

`create()` durchläuft eine Kette aus vier Prüfungen:

1. **Exaktes Duplikat** (`content_hash`): bestehende Erinnerung wird
   aktualisiert (`relevance` steigt leicht, `updated_at` neu) – keine
   Zweitkopie. Rückgabe `(memory, merged=True)`.
2. **Veralten (Supersede):** Ähnlichkeit ≥ **0.85** (difflib, normalisiert)
   mit einer älteren aktiven Erinnerung **des gleichen Typs** → die ältere
   erhält `status=superseded`, die neue setzt `supersedes_id`.
   Beispiel: „Der Nutzer heißt Max" → „Der Nutzer heißt Maxi" (0.976).
3. **Konfliktband 0.5–0.85:** beide bleiben aktiv, werden aber als
   möglicher Widerspruch markiert. Im Kontext erscheint der Hinweis
   „Nachfragen statt raten" (Systemregel `memory_conflict_ask`).
   Beispiel: „…arbeitet an Projekt Phoenix" vs. „…arbeitet an Projekt
   Berlin mit dem neuen Team" (0.702).
4. **Sonst:** neue aktive Erinnerung.

Veralten gilt bewusst nur **innerhalb** eines Typs: eine Projekt-Erinnerung
verdrängt keine Präferenz.

## 3. Suche (modular, embedding-ready)

Such-Provider-Interface (`index/remove/search/rebuild`):

| Provider | Technik | Aktiv, wenn |
|---|---|---|
| `FtsSearchProvider` | SQLite **FTS5** (unicode61, bm25 → Score 0–1) | FTS5 verfügbar |
| `LikeSearchProvider` | LIKE-Scan, Score = Begriffsabdeckung | Fallback |

- Begriffe ≥ 2 Zeichen, mit **ODER** verknüpft (`"Python" OR "FastAPI"`)
  – Treffer mit mehr Begriffen ranken höher.
- Phase 3 kann einen `EmbeddingSearchProvider` (kleines lokales
  Embedding-Modell) implementieren, ohne die Engine oder API zu ändern.
- Suche umfasst nur `active` Erinnerungen (archivierte/veraltete nicht).

## 4. Automatische Auswahl (`collect_relevant`)

Für jede Chat-Anfrage wählt die Engine maximal 5 Erinnerungen:

1. Schlagwortsuche über die Anfrage (Stopwort-Filter, max. 12 Begriffe).
   Score = Suchscore × Typgewicht `_TYPE_WEIGHT`
   (`preference` 1.25 > `project` 1.1 > `long_term` 1.0 > `conversation` 0.6).
2. **Fallback**, falls zu wenige Treffer: relevanteste aktive
   Präferenzen/Langzeit-Erinnerungen, abgewertet (Faktor 0.3) – Suchtreffer
   behalten Vortritt.
3. Konfliktprüfung: jede gewählte Erinnerung wird auf aktive
   ähnliche Gegenstücke geprüft (`conflict=True` → Kontexthinweis).

Ergebnis: `RelevantMemory(memory, score, conflict)` – der Core überträgt
diese in `MemoryCandidate` für die ContextEngine.

## 5. Merkwörter (Schritt 12 des Chat-Ablaufs)

Nicht jede Nachricht wird gespeichert – nur **explizite** Aufforderungen:

| Muster | Beispiel |
|---|---|
| `merke dir: …` | „Merke dir: Ich arbeite an Projekt Apollo" |
| `denk daran: …` / `erinnere dich: …` | „Denk daran: Ich heiße Maria" |
| `notiere: …` | „Notiere: Server-Laufzeit 14 Tage" |
| `(ab jetzt|von jetzt an): …` | „Ab jetzt: Antworte immer auf Deutsch" |

Der Typ wird über Muster erkannt (`ich heiße…` → `preference`,
`ich arbeite an…` → `project`, sonst `long_term`), die Kategorie über
eine Heuristik. Quelle: `source="chat"`, `source_ref=conversation_id`.
Normale Nachrichten erzeugen **niemals** Einträge – getestet.

## 6. Nachbereitung

- `mark_used(ids)`: setzt `last_used_at` für im Kontext verwendete
  Erinnerungen (Nutzungsnachweis, Grundlage künftiger Bewertung).
- `stats()`: Zähler für Control Center und `GET /api/core/status`
  (`total/active/superseded/archived`, `by_type`, `search_provider`).

## 7. API

| Endpoint | Verhalten |
|---|---|
| `GET /api/memory` | Liste (Filter `memory_type`, `category`, `status`) + `stats` |
| `POST /api/memory` | Anlegen (Quelle immer `user`) |
| `POST /api/memory/search` | Suche `{query, memory_type?, category?, limit}` |
| `GET /api/memory/{id}` | Einzelabruf |
| `PATCH /api/memory/{id}` | Inhalt/Kategorie/Typ/Relevanz/Status ändern |
| `DELETE /api/memory/{id}` | Löschen inkl. Index (204) |

## 8. Zusammenspiel mit anderen Engines

```
MemoryEngine.collect_relevant(session, message)
        │  RelevantMemory[] (score-geordnet, conflict-markiert)
        ▼
ZenjiCore.prepare_turn ──► ContextEngine.build(memories=…)
        │                          │  [INHALT_BEGINN]/[INHALT_ENDE]-Blöcke
        │                          ▼  „## Erinnerungen"
        │                  Zusammengeführter Systemprompt
        │
ChatService (nach Antwort) ──► remember_candidates(user_text)
        │                          → Merkwörter speichern (source=chat)
        └──────────────────────► mark_used(used_memory_ids)
```

- **ZenjiCore** orchestriert Auswahl (Schritt 5) und Nachbereitung (Schritt 12).
- **ContextEngine** setzt Erinnerungen strikt in Datenblöcke – gespeicherte
  Inhalte können niemals als Systemanweisungen wirken (Injection-Schutz
  strukturell, ergänzend zur Systemregel `injection_defense`).
- **PolicyEngine**: Widersprüche zwischen Erinnerungen löst die Regel
  `memory_conflict_ask` („nachfragen statt raten") – die Engine entscheidet
  selbst **nicht**, welche von zwei widersprüchlichen Erinnerungen „wahr" ist.
