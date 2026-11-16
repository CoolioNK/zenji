# ZENJI – Speicherarchitektur

**Grundregel:** Alle ZENJI-Daten liegen auf der externen SSD unter
`/Volumes/ZENJI-SSD` (konfigurierbar über `ZENJI_SSD_ROOT`).  Fehlt die SSD,
wird **kein** Ersatzspeicherpfad erfunden – ZENJI meldet den Zustand klar
(HTTP 503, `STORAGE_UNAVAILABLE`) und startet trotzdem, damit Status und
Frontend funktionieren.

## Layout auf der SSD

```
ZENJI-SSD/
├── ZENJI/                 ← Projektcode (backend, frontend, docs, scripts, tests)
│   ├── data/zenji.db      ← SQLite-Datenbank (s. u.: Tabellen Phase 1 + 2)
│   ├── data/zenji.db-wal  ← WAL-Journal (normal, temporär)
│   ├── run/               ← PID-Dateien (backend, frontend, ollama)
│   └── logs/              ← (falls ZENJI_LOG_DIR angepasst)
├── models/                ← Modellgewichte (OLLAMA_MODELS von Ollama gelesen)
├── datasets/              ← für Phase 3 (Training/Daten)
├── backups/               ← Datenbank-Backups
├── environments/          ← virtuelle Python-Umgebung (zenji-venv)
└── logs/                  ← zenji-backend.log, backend.log, frontend.log, ollama.log
```

## Datenbanktabellen (Phase 1 + 2 + 3)

| Tabelle | Inhalt |
|---|---|
| `conversations`, `messages` | Chats (Phase 1, unverändert) |
| `settings` | Laufzeit-Einstellungen (Phase 1; v0.5.0: Gruppe `web_intelligence`) |
| `personalities` | Persönlichkeitsprofile (Seed: 5 Systemprofile, „Zenji" aktiv; v0.3.0 +6 Achsen) |
| `policies` | Verhaltensregeln (Seed: 8 System + 1 Nutzerregel; v0.4.0 neu `insult_banter`) |
| `memories` | Erinnerungen (Typ, Quelle, Relevanz, Status, content_hash indiziert) |
| `memories_fts` | FTS5-Volltextindex über Erinnerungen (virtual table) |
| `schema_version` | Versions-Metadaten (Spiegel von `PRAGMA user_version`) |
| `research_sessions` | Recherche-Durchläufe: Frage, Modus, Status, Plan-/Report-JSON, Dauer (v0.5.0) |
| `search_queries` | Ausgeführte Suchanfragen (Query, Anbieter, Trefferzahl) (v0.5.0) |
| `search_results` | Gefundene Treffer (URL, Titel, Domain, Rang) (v0.5.0) |
| `sources` | Registrierte Quellen: original/canonical URL, Domain, Metadaten, Hash, Typ (v0.5.0) |
| `source_snapshots` | Lokale Inhaltskopien: Text, Hash, Extractor, Zeichenzahl (v0.5.0) |
| `citations` | Belegaussagen je Recherche: statement, marker, source_id (v0.5.0) |
| `research_cache` | Such-/Abruf-Cache mit TTL (Key, Payload, created_at) (v0.5.0) |

Migrationen: `PRAGMA user_version = 5` (aktuelle Stufe). Schema-Änderungen
sind nur additiv; bestehende Konversationen bleiben bei jedem Start erhalten
(geprüft in `tests/test_migrations.py`). Migration 2→3 (v0.3.0) ergänzt
sechs Persönlichkeits-Achsen per `ALTER TABLE` und aktualisiert System-
regeln/-profile aus den Seeds. Migration 3→4 (v0.4.0) seedet additiv nach
(`insult_banter`) und aktualisiert die Systemregel-Texte. Migration 4→5
(v0.5.0) legt die sieben Web-Intelligence-Tabellen an – reiner Version-
Bump: Seeds (9 Regeln/8 System, 5 Profile) bleiben unverändert. Details:
docs/DEVELOPMENT.md.

## Datenschutz im Gedächtnis

- Erinnerungen liegen **ausschließlich** lokal in `zenji.db` (FTS-Index
  ebenfalls lokal). Keine externe Übertragung, kein Telemetrie-Pfad.
- Jede Erinnerung zeigt Quelle (`source`) und Bezug (`source_ref`) —
  im Control Center und in der API einsehbar.
- Löschen (UI oder `DELETE /api/memory/{id}`) entfernt Eintrag **und**
  Indexrest endgültig. Archivieren ist die weiche Alternative.
- Automatische Speicherung passiert nur bei expliziten Merkwörtern
  („Merke dir: …"); normale Nachrichten werden nicht persistiert.

## Datenschutz im Web (v0.5.0)

- Recherche-Daten (Sessions, Suchanfragen, Quellen, Snapshots, Cache)
  liegen **ausschließlich lokal** in `zenji.db`; übertragen wird nur,
  was eine Recherche braucht (Suchanfrage an SearXNG/Brave, Abruf
  öffentlicher Seiten).
- Nutzerkontrolle: Recherche-Sessions, einzelne Quellen (+Snapshots)
  und der gesamte Cache sind per API/Control Center löschbar
  (docs/WEB_SECURITY.md §6).
- Der Brave-API-Schlüssel wird gespeichert, aber **nie** aus der API
  zurückgegeben (`brave_api_key_set` statt Wert).
- Recherche-Reports gehen nicht automatisch ins Gedächtnis – nur der
  Chatverlauf enthält die belegte Antwort.

## Umgebungsvariablen

| Variable | Bedeutung | Standard |
|---|---|---|
| `ZENJI_SSD_ROOT` | Wurzel der externen SSD | `/Volumes/ZENJI-SSD` |
| `ZENJI_STORAGE_DIR` | Projektverzeichnis | `<SSD_ROOT>/ZENJI` |
| `ZENJI_DB_PATH` | SQLite-Datei | `<STORAGE>/data/zenji.db` |
| `ZENJI_LOG_DIR` | Log-Verzeichnis | `<SSD_ROOT>/logs` |
| `OLLAMA_MODELS` | Modellgewichte (vom **Ollama-Prozess** gelesen) | von start.sh gesetzt: `<SSD_ROOT>/models` |

Keine fest codierten Pfade im Anwendungscode – jede Angabe ist überschreibbar
(`backend/.env` oder echte Umgebungsvariable).

## SSD während des Betriebs trennen

Erkennung und Umgang:

- Datenbank-/Dateioperationen fangen Schreibfehler ab und übersetzen sie in
  `StorageUnavailableError` → `HTTP 503` mit klarer Meldung.
- `/api/health` prüft den Pfad aktiv (Vorhandensein + Schreibprobe ohne
  Datenverlust) → Statusleiste im Frontend zeigt „nicht verbunden".
- Das Backend **crasht nicht**; beim Wiederanschließen der SSD laufen die
  Operationen ohne Neustart weiter (SQLite öffnet die Datei pro Verbindung neu).
- Der Chat speichert Teilantworten – auch bei Abbruch bleibt der Verlauf
  konsistent, sobald die SSD wieder verfügbar ist.

## Modellgewichte auf der SSD

Ollama liest `OLLAMA_MODELS` beim **Start des Servers**:

```bash
OLLAMA_MODELS=/Volumes/ZENJI-SSD/models ollama serve
```

- `scripts/start.sh` startet Ollama automatisch so (falls nicht läuft).
- Läuft Ollama bereits ohne SSD-Modelspeicher, meldet `start.sh` einen
  Hinweis; korrigieren mit `./scripts/restart_ollama.sh`.
- Modell laden: `./scripts/download_model.sh` (≈ 5 GB für qwen3:8b, Q4).

## Backups (Empfehlung, Phase 2)

Die Datenbank ist eine einzige Datei: `<SSD>/ZENJI/data/zenji.db`.
Backup = Datei kopieren (vorher ZENJI stoppen oder SQLite-
`VACUUM INTO` verwenden).  Vorgesehener Zielordner: `<SSD>/backups/`.
