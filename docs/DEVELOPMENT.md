# ZENJI – Entwicklung (Phase 1)

## Voraussetzungen

| Werkzeug | Version | Prüfen |
|---|---|---|
| macOS | Apple Silicon (M4, 16 GB getestet) | – |
| externe SSD | unter `/Volumes/ZENJI-SSD` | `./scripts/check_environment.sh` |
| Python | 3.12.x | `python3.12 --version` |
| Node.js | ≥ 20 | `node --version` |
| Ollama | beliebig aktuell | `ollama --version` |
| Git | beliebig | `git --version` |

## Erster Aufbau (empfohlen)

```bash
cd ZENJI                       # Projektverzeichnis (Quelle)
./scripts/check_environment.sh # Umgebung prüfen (SSD kritisch!)
./scripts/setup.sh             # → kopiert Projekt auf SSD, erstellt venv dort, installiert alles
cd /Volumes/ZENJI-SSD/ZENJI
./scripts/download_model.sh    # qwen3:8b laden (~5 GB, Gewichte → SSD)
./scripts/start.sh             # Backend + Frontend starten
# → http://localhost:5173
./scripts/stop.sh              # beenden
```

## Entwicklung ohne SSD (nur Quelltext/Tests)

Tests und Backend-Entwicklung laufen ohne SSD – der Speicherpfad wird per
Umgebungsvariable auf ein temporäres Verzeichnis gelenkt (ausschließlich für
Tests; das Produktivsystem verlangt die SSD):

```bash
cd backend
../.venv/bin/python -m pytest tests -q     # 87 Tests, ohne Modell, ohne Ollama
ZENJI_SSD_ROOT=$(mktemp -d) ../.venv/bin/uvicorn app.main:app --port 8000
```

## Projektstruktur

```
ZENJI/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI-Fabrik + Lifespan
│   │   ├── core/                 # config, exceptions, logging, storage, extensions
│   │   ├── api/routes/           # health, models, settings, conversations, chat
│   │   ├── engines/              # llm_engine, model_manager, providers/
│   │   ├── services/             # chat_service, conversation_service, settings_service
│   │   ├── database/             # database, models, repositories/
│   │   ├── schemas/              # Pydantic-API-Schemata
│   │   └── interfaces/           # ABCs für Phase-2-Engines
│   ├── tests/                    # pytest (87 Tests)
│   ├── requirements.txt          # getestete Versionen
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/           # Sidebar, ChatArea, Composer, SettingsPanel, …
│   │   ├── pages/ChatPage.tsx    # Layout
│   │   ├── hooks/                # useChat (SSE), useHealth, useConversations, useSettings
│   │   ├── services/             # api.ts (REST), sse.ts (SSE-Parser)
│   │   ├── types/                # Spiegel der Backend-Schemata
│   │   └── styles/index.css      # Tailwind v4 Theme (Graphit + Jade)
│   └── package.json
├── docs/                         # ARCHITECTURE, API, DEVELOPMENT, STORAGE
├── scripts/                      # check_environment, setup, start, stop, restart_ollama, download_model
└── README.md
```

## Backend-Befehle

```bash
cd backend
../.venv/bin/python -m pytest tests            # alle Tests
../.venv/bin/python -m pytest tests -k stream  # gefiltert
../.venv/bin/uvicorn app.main:app --reload     # Dev-Server (braucht ZENJI_SSD_ROOT)
```

## Frontend-Befehle

```bash
cd frontend
npm install       # einmalig
npm run dev       # Vite-Devserver (Proxy /api → localhost:8000)
npm run build     # TypeScript-Prüfung + Produktionsbuild (dist/)
```

## Konventionen

- **Sprache:** Nutzergerichtete Meldungen deutsch, Code/Bezeichner englisch.
- **Pfade:** nie hart codiert; immer über `app.core.config.Settings` bzw.
  `ZENJI_*`-Variablen. SSD-Pflicht gehört in `core/storage.py`.
- **Fehler:** fachliche Ausnahmen erben von `ZenjiError` (mit `code`,
  `status_code`) → automatisch einheitliches JSON-Fehlerformat.
- **Provider:** neue Modellserver nur über `engines/providers/` + Registry
  (`register_provider`); niemals Ollama direkt im Chat-Service aufrufen.
- **DB:** ORM-Modelle in `database/models.py`; Repositories liefern
  ORM-Objekte, Services mappen auf API-Schemata.
- **Dependencies:** `requirements.txt` enthält die getesteten Pins; Änderungen
  nur mit erfolgreicher Testlauf-Bestätigung.

## Git

Das Projekt ist ein eigenständiges Git-Repository (`ZENJI/`). `node_modules`,
`.venv`, `dist`, Logs, Datenbanken und `.env` sind ignoriert (.gitignore).
