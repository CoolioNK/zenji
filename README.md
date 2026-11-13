# ZENJI

Ein eigenständiges, modulares KI-System für lokale Geräte (Apple Silicon).
Phase 1: Fundament, lokale KI (Ollama/Qwen3 8B), Chat mit Streaming,
Konversationsverwaltung, Konfigurationssystem und Speicherarchitektur auf
externer SSD.

> **Leitprinzip:** ZENJI ist ein eigenständiges KI-System. Das Sprachmodell
> ist nur sein Denk-Kern. Architektur, Steuerung, Persönlichkeit,
> Parameterverwaltung und zukünftige Erweiterungen gehören zum
> selbst entwickelten ZENJI-System.

## Schnellstart (macOS, externe SSD)

```bash
cd ZENJI
./scripts/check_environment.sh     # SSD, Python 3.12, Node, Ollama prüfen
./scripts/setup.sh                 # Projekt + Struktur + venv auf die SSD
cd /Volumes/ZENJI-SSD/ZENJI
./scripts/download_model.sh        # qwen3:8b laden (~5 GB → SSD)
./scripts/start.sh                 # Backend :8000 · Frontend :5173
```

Danach: **http://localhost:5173** · Stop: `./scripts/stop.sh`

**Ohne SSD startet ZENJI nicht unkontrolliert:** `check_environment.sh` und
`start.sh` brechen mit klarer Meldung ab (`kein Ersatzspeicherpfad`). Läuft
das Backend bereits und wird die SSD getrennt, bleiben Status/Health
erreichbar und alle Datenoperationen melden `STORAGE_UNAVAILABLE`.

## Was Phase 1 bietet

- **Chat** mit SSE-Streaming, Abbruchmöglichkeit, Teilantwort-Speicherung
- **Mehrere Konversationen**: anlegen, umbenennen, löschen, Verlauf
- **Einstellungen** zur Laufzeit änderbar: Temperature, Top P/K,
  Repetition Penalty, Output-Tokens, Context Window, Streaming, Ollama-
  Parameter (Timeout, Keep-Alive), Persönlichkeit/System-Prompt
- **Provider-Abstraktion**: Ollama austauschbar (llama.cpp & Co. in Phase 2)
- **Statusleiste**: Backend, Ollama-Verbindung, geladenes Modell, SSD-Zustand
- **Robuste Fehler**: verständliche Meldungen bei fehlendem Modell, offline
  Ollama, fehlender SSD – kein Crash, keine unklaren Abstürze
- **87 Backend-Tests** (Mocking für Modellanfragen; laufen ohne Modell/SSD)
- **Erweiterungspunkte** für Phase 2: Policy-, Memory-, Web-, Tool-, Plugin-,
  RAG-, Image-Engine (dokumentierte Schnittstellen + Registry)

## Dokumentation

| Datei | Inhalt |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Schichten, Datenfluss, Erweiterungspunkte |
| [docs/API.md](docs/API.md) | Alle Endpunkte inkl. SSE-Protokoll |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Setup, Tests, Konventionen |
| [docs/STORAGE.md](docs/STORAGE.md) | SSD-Layout, OLLAMA_MODELS, Trennverhalten |

## Projektstatus

- Phase 1 **abgeschlossen** (Details in `docs/ROADMAP.md` bzw. Abschlussbericht)
- Modellverfügbarkeit: `qwen3:8b` muss einmalig geladen werden
  (`./scripts/download_model.sh`), sobald die SSD verbunden ist
