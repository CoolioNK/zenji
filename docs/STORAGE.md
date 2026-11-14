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

## Datenbanktabellen (Phase 1 + 2)

| Tabelle | Inhalt |
|---|---|
| `conversations`, `messages` | Chats (Phase 1, unverändert) |
| `settings` | Laufzeit-Einstellungen (Phase 1) |
| `personalities` | Persönlichkeitsprofile (Seed: 4 Systemprofile) |
| `policies` | Verhaltensregeln (Seed: 5 System + 1 Nutzerregel) |
| `memories` | Erinnerungen (Typ, Quelle, Relevanz, Status, content_hash indiziert) |
| `memories_fts` | FTS5-Volltextindex über Erinnerungen (virtual table) |
| `schema_version` | Versions-Metadaten (Spiegel von `PRAGMA user_version`) |

Migrationen: `PRAGMA user_version = 2` (aktuelle Stufe). Schema-Änderungen
sind nur additiv; bestehende Konversationen bleiben bei jedem Start erhalten
(geprüft in `tests/test_migrations.py`). Details: docs/DEVELOPMENT.md.

## Datenschutz im Gedächtnis

- Erinnerungen liegen **ausschließlich** lokal in `zenji.db` (FTS-Index
  ebenfalls lokal). Keine externe Übertragung, kein Telemetrie-Pfad.
- Jede Erinnerung zeigt Quelle (`source`) und Bezug (`source_ref`) —
  im Control Center und in der API einsehbar.
- Löschen (UI oder `DELETE /api/memory/{id}`) entfernt Eintrag **und**
  Indexrest endgültig. Archivieren ist die weiche Alternative.
- Automatische Speicherung passiert nur bei expliziten Merkwörtern
  („Merke dir: …"); normale Nachrichten werden nicht persistiert.

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
