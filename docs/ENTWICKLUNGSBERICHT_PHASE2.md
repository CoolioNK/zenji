# ZENJI – Entwicklungsbericht Phase 2: Core Intelligence

**Datum:** 14. November 2026
**Version:** 0.2.0 · Commit `26e364a`
**Status:** ✅ Abgeschlossen — Backend, Frontend, Tests, Doku, Live-Betrieb
**Vorgänger:** Phase 1 „Fundament, lokale KI" (v0.1.0)

---

## 1. Zielsetzung

Phase 2 verwandelt ZENJI von einem Chatsystem mit fest eingebautem Persona-
Prompt in ein **eigenständiges KI-System mit steuerbarer Identität, Regeln,
Gedächtnis und nachvollziehbarer Kontexterstellung**. Leitprinzip: Das
Sprachmodell erzeugt Antworten — ZENJI entscheidet, mit welcher Identität,
welchen Regeln, welchen Erinnerungen und welchem Kontext.

Alle Kernforderungen wurden umgesetzt:

| Forderung | Umsetzung |
|---|---|
| Kein Fake, keine Zierfunktionen | Jede Funktion verarbeitet echte Daten; Tests belegen Verhalten |
| LLM-unabhängige Architektur | Modell ist nur Generierungskern; Engines kennen keinen Provider |
| Konfigurierbare Persönlichkeit | Profile in DB + Seed-JSON, nicht in Python hart codiert |
| Regelsystem mit Prioritäten | PolicyEngine mit Konfliktauflösung + System-Schutz |
| Echtes Gedächtnis | 4 Typen, Quellen, Dedupe, Veralten, Nutzerkontrolle |
| Kontext nachvollziehbar | ContextPlan + `/api/core/context-preview` |
| Datenschutz | Nur lokale Speicherung, Merkwörter opt-in, Löschen inkl. Index |
| Phase-1-Kompatibilität | 87 Bestandstests grün, Chatpfad ohne Core unverändert |

---

## 2. Implementierung

### 2.1 Personality Engine (`app/engines/personality_engine.py`)

- **Datenmodell** (`personalities`): Name, Identität, Grundpersönlichkeit
  (`neutral/professional/friendly/casual/custom`), Kommunikationsstil,
  Formalität/Humor/Direktheit/Kreativität (0–1), Antwortlänge, Sprache,
  Situationsverhalten (JSON), `is_system`, `is_active`.
- **Seed** `backend/app/config/personalities.json`: Neutral (Standard aktiv),
  Professional, Friendly, Casual — idempotent eingespielt, niemals
  überschreibt das Seed eine Nutzeraktivierung.
- **Kompilierung** `compile_context()`: deterministischer Block
  „## Persönlichkeit"; skalare Werte werden über Stufentabellen in
  Sprachniveaus übersetzt (z. B. Formalität 0.5 → „ausgeglichen").
- **Genau ein aktives Profil**: `activate()` in einer Transaktion; der
  Chatpfad liest `require_active()`.
- **Schutzregeln**: Systemprofile löschgeschützt (409
  `PERSONALITY_PROTECTED`), aktive Profile löschgeschützt, Namensdubletten
  abgelehnt (409 `PERSONALITY_NAME_TAKEN`), Nutzerprofile frei erstellbar.

### 2.2 Policy Engine (`app/engines/policy_engine.py`)

- **Datenmodell** (`policies`): ID (ASCII-Slug), Anweisung, Priorität 0–100,
  aktiviert/aktivierbar, Kategorie, Scope (`global/personality/conversation/
  user`), Quelle (`system/user`).
- **Seed** `backend/app/config/system_policies.json`:

| Regel | P | Zweck |
|---|---|---|
| zenji_identity | 100 | Identität kommt aus ZENJI, nicht vom Modell |
| injection_defense | 100 | Datenblöcke strikt als Daten behandeln |
| honesty_first | 95 | Nicht wissen sagen statt spekulieren |
| memory_conflict_ask | 92 | Bei widersprüchlichen Erinnerungen nachfragen |
| language_follow_user | 90 | In der Sprache des Nutzers antworten |
| direct_communication | 50 | **Nutzerregel** (source=user) |

- **Kompilierung**: Sortierung System vor Nutzer → Priorität absteigend →
  Name; ein Block „## Regeln" mit markierten Prioritäten `[P100|identität]`.
- **Konflikterkennung**: Anweisungsähnlichkeit (difflib, Schwelle 0.82);
  höherer Priorität gewinnt, Verlierer fällt aus dem Kontext, bleibt aber
  in der DB und wird **transparent** als Konflikt berichtet
  (`GET /api/policies` → `conflicts[]`).
- **System-Schutz**: `PATCH/DELETE` auf Systemregeln → 403
  `POLICY_SYSTEM_PROTECTED`; `source: system` per API nicht anlegbar
  (Schema lehnt das Feld mit 422 ab).
- **Injection-Erkennung** `check_incoming`: 9 Muster (de/en) markieren
  Injection-Versuche als Flags — fail-soft, blockiert nie den Chat.

### 2.3 Memory Engine (`app/engines/memory_engine.py`)

- **4 Typen**: `conversation`, `long_term`, `preference`, `project` —
  mit Typgewichten (Präferenz 1.25 > Projekt 1.1 > Langzeit 1.0 >
  Gespräch 0.6) für die Kontextauswahl.
- **Jede Erinnerung**: ID, Inhalt, Kategorie, Typ, Quelle (`chat`/`user`),
  Bezugsangabe (`source_ref`), Relevanz, Status, `content_hash`
  (SHA-256, indiziert), `supersedes_id`, `last_used_at`, Zeitstempel.
- **Duplikaterkennung**: exakt identischer Inhalt (normalisiert, Hash)
  führt zu Merge — Relevanz steigt, keine Zweitkopie.
- **Veralten (Supersede)**: Ähnlichkeit ≥ 0.85 innerhalb desselben Typs →
  neuere Erinnerung verdrängt ältere (Status `superseded`, Verweis
  `supersedes_id`). Gemessen: „Max"→„Maxi" = 0.976.
- **Widerspruchsband 0.5–0.85**: beide aktiv, markiert; im Kontext erscheint
  „Nachfragen statt raten" (geregelt durch Systemregel
  `memory_conflict_ask`). Gemessen: Phoenix/Berlin-Team = 0.702.
- **Modulare Suche**: `FtsSearchProvider` (SQLite FTS5, bm25-normalisiert)
  mit `LikeSearchProvider`-Fallback, gleiches Interface — Phase 3 kann
  einen EmbeddingProvider ohne Umbau einhängen. Begriffe ODER-verknüpft.
- **Automatische Auswahl** `collect_relevant()`: max. 5 Erinnerungen pro
  Anfrage — Schlagwortsuche über die Nutzeranfrage, Fallback auf
  relevante Präferenzen/Langzeit-Erinnerungen (abgewertet), Konflikt-
  markierung je Treffer.
- **Merkwörter (opt-in)**: „merke dir/denk daran/erinnere dich/notiere/
  (ab jetzt|von jetzt an): …" erzeugen Erinnerungen (`source=chat`); Typ
  über Muster, Kategorie über Heuristik. Normale Nachrichten werden
  **niemals** automatisch gespeichert (getestet).
- **Nutzungsnachweis**: `mark_used()` setzt `last_used_at` für im Kontext
  verwendete Erinnerungen; `stats()` liefert Zähler fürs UI.

### 2.4 Context Engine (`app/engines/context_engine.py`)

- **Ein zusammengeführter Systemprompt** mit beschrifteten Abschnitten:
  `## Identität` → `## Persönlichkeit` → `## Regeln` → `## Erinnerungen` →
  `## Zusammenfassung älterer Nachrichten` → `## Sicherheitshinweis`.
  Rollenfolge konform: `["system", "user", …]`.
- **Token-Budget**: `estimate = ceil(len/3.6)`; Budget =
  `num_ctx − num_predict − 256`, Minimum 512 — heuristisch, ohne
  Tokenizer-Abhängigkeit.
- **Kürzungsreihenfolge**: Erinnerungen (schlechtester Score zuerst) →
  älteste Verlaufsnachrichten (jüngste bleiben; `HISTORY_KEEP_MIN=4`) →
  Verdrängte Nachrichten laufen in eine **extraktive Zusammenfassung**
  (120 Zeichen/Nachricht, max. 12 Einträge) — keine Fake-LLM-Summary.
- **Datenblöcke** `[INHALT_BEGINN]/[INHALT_ENDE]` um jede Erinnerung:
  struktureller Injection-Schutz — gespeicherte Inhalte sind im Prompt
  exakt als Daten erkennbar, kombiniert mit der Regel `injection_defense`.
- **Nachvollziehbarkeit** `ContextPlan`: Abschnitte mit Token-Schätzungen,
  behalten/verworfen-Zähler, Konflikte, Flags, der exakte Systemtext und
  die genutzten Erinnerungs-IDs — Grundlage von `/api/core/context-preview`.

### 2.5 ZENJI Core (`app/services/zenji_core.py`)

Orchestriert die Spezifikationsschritte 1–12 pro Nachricht:

1. Nachricht empfangen (ChatService übergibt) → 2. Settings laden →
3. Persönlichkeit laden/kompilieren → 4. aktive Regeln kompilieren →
5. relevante Erinnerungen suchen → 6. Kontext bauen → 7. Validierung
(Budget-Plan + Injection-Flags, fail-soft) → 8.–11. LLM-Aufruf/Antwort
(bleibt im ChatService) → 12. Nachbereitung: Merkwörter speichern,
`last_used_at` setzen.

Grundsätze umgesetzt: **keine** DB-Details und **keine** Provider-Logik im
Core; jede Engine fail-soft — ein Fehler reduziert den Kontext, blockiert
aber nie die Antwort. `ChatService` hat einen **optionalen** Core: ohne
Core gilt exakt Phase-1-Verhalten (durch Tests fixiert).

### 2.6 Datenbank & Migration

- Neue Tabellen: `personalities`, `policies`, `memories` (+ FTS
  `memories_fts`), `schema_version`. `content_hash` indiziert.
- **Migration**: `PRAGMA user_version` + `schema_version`-Spiegel,
  aktuelle Stufe **2**; `create_all` (additiv) + idempotente Seeds beim
  Lifespan-Start. Tests simulieren eine Phase-1-DB (Tabellen-Drop,
  Version 0) und belegen: **keine Konversation geht verloren**.
- Echte Live-Migration verifiziert: `ZENJI/data/zenji.db` in-place auf
  Stufe 2 — 2 Konversationen / 38 Nachrichten vollständig erhalten,
  4 Profile + 6 Regeln geseedet, `search_provider=fts5`.

### 2.7 API (Phase 2)

| Endpoint | Methode(n) | Anmerkung |
|---|---|---|
| `/api/personality` | GET/POST | Liste (aktiv zuerst) / Anlegen (201) |
| `/api/personality/{id}` | PATCH/DELETE | Edit / 204; 409 bei Schutz |
| `/api/personality/{id}/activate` | POST | Einzelaktiv |
| `/api/personality/{id}/preview` | GET | Kompilierter Block |
| `/api/policies` | GET | Liste **inkl. `conflicts[]`, `disabled_count`** |
| `/api/policies/{id}` | PATCH/DELETE | 403 bei Systemregel |
| `/api/memory` | GET/POST | Filter + `stats` / Anlegen (`source=user`) |
| `/api/memory/search` | POST | FTS5/LIKE mit Score |
| `/api/memory/{id}` | GET/PATCH/DELETE | volle Nutzerkontrolle |
| `/api/core/status` | GET | Identität, Regeln, Gedächtnis, Modell |
| `/api/core/context-preview` | GET | Entwurf ohne LLM-Aufruf |

Alle Endpunkte validiert (Pydantic, `extra=forbid` bei Create-Schemata,
Bereichsklemmung), einheitliches Fehlerformat `{"error": {code, message}}`.

### 2.8 Frontend — ZENJI Control Center

- Rechte Schublade (600 px) mit vier Tabs: **Personality** (Profile
  ansehen/bearbeiten/aktivieren/löschen, Kompilier-Vorschau, Schieberegler),
  **Policies** (Regeln, Prioritäten, Konflikte, System-Schutz), **Memory**
  (Suche, Statusfilter, Edit/Löschen, Quell-/Nutzungsanzeige, Zähler),
  **Core Status** (Kern-Zustände, Kontext-Vorschau mit Auslastungsbalken,
  Abschnittsliste, zusammengesetzter Systemprompt, Nachrichtenfolge).
- Design unverändert: Graphit + Jade, minimalistisch, keine Dashboard-Karten.
- Neuer Sidebar-Button „Control Center"; Hooks
  `usePersonalities/usePolicies/useMemories/useCoreStatus`; Typen + REST-
  Client erweitert. Build: 274.24 kB JS / 83.03 kB gzip, TS-Fehler 0.

---

## 3. Tests

**178 Tests grün in 1.5 s** — 87 Phase-1 (unverändert) + 91 neue:

| Suite | Anzahl | Deckt ab |
|---|---|---|
| test_migrations.py | 5 | Schema-Stufen, Seed-Idempotenz, Phase-1-Datenerhalt, Hash-Index |
| test_personality_engine.py | 12 | CRUD, Aktivierung, Schutz, Kompilierung, JSON-Verhalten |
| test_policy_engine.py | 15 | Sortierung, Konflikte, Schutz, Klemmung, Injection-Flags |
| test_memory_engine.py | 17 | Dedupe/Merge, Veralten, Konfliktband, Suche, Merkwörter, Stats |
| test_context_engine.py | 12 | Budget, Abschnitte, Dedupe, Verlaufskürzung, Datenblöcke, Flags |
| test_zenji_core.py | 8 | Voller Chat mit Core, Merkwort-E2E, Fallback ohne Core |
| test_api_phase2.py | 22 | Alle Endpunkte, Validierung, Fehlercodes, Chat-Integration |

Bedingungen: FakeProvider statt LLM, Temp-DB statt SSD — **kein Netz, kein
Modell, kein Ollama** nötig. Im Testlauf gefundene und behobene Bugs:
naive/aware-Zeitvergleiche (`_as_utc`), Typ-Scoping beim Veralten,
FTS-OR-Semantik, Identitäts-Header-Präpend, dict→JSON bei
Situationsverhalten, Verlaufs-Token-Schätzung.

---

## 4. Live-Verifikation (echtes System)

Nach Neustart (Backend/Frontend/Ollama mit qwen3:8b):

- `/api/core/status` → Version 0.2.0, Persönlichkeit **Neutral**, 6 aktive
  Regeln, 0 Konflikte, FTS5 aktiv, Modell qwen3:8b, ctx 8192.
- Echte Migration: Stufe 2, Konversationen/Nachrichten erhalten.
- Memory-CRUD + Suche live: Anlegen (201), FTS-Treffer (Score 1.0),
  Löschen (204).
- **End-to-End mit Modell**: Chat „Merke dir: Das Lieblingsprojekt des
  Nutzers heißt Zenji Phase 2" → gestreamte Antwort (SSE start/delta*/done)
  → Erinnerung automatisch mit `source=chat` angelegt → Kontext-Preview
  der Folgefrage zeigt sie im `[INHALT_BEGINN]`-Datenblock: 646/5888 Tokens
  (11 %), Abschnitte identity 126 / personality 198 / policies 260 /
  memories 53 / history 39.
- Control Center im Browser: alle vier Tabs interaktiv, Kontext-Vorschau
  rendert den zusammengefassten Systemprompt, keine Konsolenfehler.

---

## 5. Architektur-Entscheidungen

1. **Konfiguration statt Code**: Profile/Regeln in DB + Seed-JSON — der
   Nutzer formt ZENJI, ohne den Kernel zu berühren.
2. **Datenblöcke statt Tag-Delimiter**: `[INHALT_BEGINN]/[INHALT_ENDE]` —
   robust gegen Inhaltsverlust und Modellverwirrung; Winkelklammern
   vermeiden Eskalationsprobleme mit Strip-Logik des Providers.
3. **Ein Systemprompt statt vieler Systemnachrichten**: stabiler für
   lokale Modelle, token-effizient, eindeutige Abschnitts-Reihenfolge.
4. **Fail-soft überall**: Policy-/Memory-/Verlaufsfehler degradieren den
   Kontext, brechen aber nie den Chat; nur echte Infrastrukturfehler
   (SSD/Provider/Modell) enden mit HTTP-Fehlern.
5. **Heuristische Token-Schätzung** (len/3.6): bewusst ohne Tokenizer —
   konservativ, portabel, für Deutsch ausreichend genau.
6. **Optional-Core-Muster**: ChatService mit/ohne Core hält Phase-1-
   Kompatibilität hart (testgetrieben) und erlaubt gestuften Ausbau.
7. **Migration ohne Alembic**: `PRAGMA user_version` + additive Schritte —
   minimal, prüfbar, keine zusätzliche Abhängigkeit.

---

## 6. Grenzen (bewusst, nicht versteckt)

- **Token-Schätzung** ist heuristisch (±15 %); echte Zahlen liefert erst
  eine Tokenizer-Anbindung (Phase 3 optional).
- **Ähnlichkeitsheuristiken** (difflib) erkennen wörtlich ähnliche
  Widersprüche; semantische Gegensätze („liebt"/„hasst" = 0.886) liegen
  fälschlich im Supersede-Band → Phase 3: Embeddings + Kontradiktions-
  Erkennung verbessern das. Kein Datenverlust: beide Erinnerungen bleiben
  in der DB (Status/Markierung), nichts wird still gelöscht.
- **Merkwort-Erkennung** ist Deutsch-fokussiert (Englisch folgt in Phase 3).
- **Zusammenfassung** älterer Nachrichten ist extraktiv (Anfänge), keine
  semantische Kondensierung.
- **Kein Tool Calling/Web/RAG** — das ist ausdrücklich Phase 3.
- Supersede prüft nur aktive, gleichartige Erinnerungen; komplexe
  zeitliche Logik („bis Juli" vs. „seit August") folgt in Phase 3.

## 7. Empfehlungen für Phase 3

1. **Embedding-Suche**: kleiner lokales Embedding-Modell als dritter
   `SearchProvider` — semantische Erinnerungstreffpunkte, bessere
   Widerspruchserkennung (Kontradiktionspaare wie liebt/hasst).
2. **Tool Calling**: Funktionsdeklaration + Ausführung im Core
   (Schritt 7 wird zur Tool-Schleife); Ergebnis-Blöcke gleichermaßen
   als Daten markieren.
3. **Web-Zugriff**: Suche/Analyse mit unlauter-Injection-Diagnose;
   Ergebnisse ausschließlich in Datenblöcken.
4. **Semantic Summaries**: optionale echte Zusammenfassung mit kleinem
   Modell (offline), als Abschnitt statt extraktiver Liste.
5. **Mehrsprachige Merkwörter + Erinnerungspflege-Assistent**
   (Vorschlag „veraltete Erinnerungen aufräumen").
6. **RAG/Dateien**: Dokumente als `source=file`-Erinnerungen mit
   Chunk-Index — wiederverwendet FTS-/Embedding-Provider.
7. **Backups automatisieren**: `VACUUM INTO` nach Änderungen über
   Schwelle, Zielordner `<SSD>/backups/` (Struktur ist vorbereitet).

---

## 8. Fazit

Phase 2 liefert das versprochene Kernstück: ZENJI hat jetzt eine
**steuerbare Identität**, ein **regelbasiertes Verhalten mit
Konfliktauflösung**, ein **echtes, transparentes Gedächtnis** und eine
**nachvollziehbare Kontexterstellung** — vollständig lokal, LLM-unabhängig,
mit 178 grünen Tests und ohne den Rückstand aus Phase 1 zu beschädigen.
Der Nutzer sieht jederzeit (Control Center, Kontext-Vorschau), was ZENJI
weiß, welche Regeln gelten und was exakt an das Modell geht.
