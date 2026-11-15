# ZENJI – Entwicklung (Phase 1 + 2)

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
../.venv/bin/python -m pytest tests -q     # 178 Tests, ohne Modell, ohne Ollama, ohne Netz
ZENJI_SSD_ROOT=$(mktemp -d) ../.venv/bin/uvicorn app.main:app --port 8000
```

## Phase 2: Migrationen und Seeds

Die Datenbank versioniert sich selbst (`PRAGMA user_version` + Tabelle
`schema_version`, aktuelle Stufe **3**):

- `app/database/migrations.py`: `run_migrations(engine)` läuft beim
  App-Start (Lifespan), ist **idempotent** und nur additiv — bestehende
  Konversationen/Nachrichten/Einstellungen bleiben unverändert.
- Seeds (idempotent, keine Nutzerdaten-Überschreibung):
  - `app/config/personalities.json` → 5 Systemprofile (Zenji aktiv,
    Begleiter-Persönlichkeit v0.3.0)
  - `app/config/system_policies.json` → 7 Systemregeln + 1 Nutzerregel
  - `app/config/communication_modes.json` → 5 Kommunikationsmodi
    (kein DB-Seed, direkter Import in der CommunicationEngine)
- Migration **2→3 (v0.3.0)**: ergänzt sechs Persönlichkeits-Achsen per
  idempotentem `ALTER TABLE` (PRAGMA-Prüfung), aktualisiert die Texte
  geschützter Systemregeln und die neuen Achsen von Systemprofilen aus
  den Seeds, seeden additiv nach und aktiviert „Zenji" — aber nur, wenn
  aktiv gar nichts oder nur das Seed-Standardprofil „Neutral" läuft.
  Ein angepasster Persona-Prompt (Settings) wird nur bei **exakt** dem
  v0.2.0-Default ersetzt (`LEGACY_PERSONA`-Match).
- `MemoryEngine.init_search(session)` richtet FTS5 (`memories_fts`)
  ein; fehlt FTS5, nutzt die Suche automatisch den LIKE-Provider.
- Migrationstests simulieren eine Phase-1-Datenbank (Tabellen-Drop,
  `user_version=0`) und prüfen, dass Konversationen erhalten bleiben;
  `test_companion_personality.py` simuliert eine Phase-2-Datenbank
  (`user_version=2`) und prüft die 2→3-Überführung inklusive
  Nutzerwahl-Schutz.

Neue Tabellen/Spalten: `create_schema()` (`create_all`) legt fehlendes
an, eine neue Migrationsstufe füllt/transformiert, `LATEST_VERSION` +
Test erhöhen.

## Teststruktur (Phase 2 + v0.3.0)

| Datei | Fokus |
|---|---|
| `test_migrations.py` | Schema-Stufen, Seeds idempotent, Phase-1-Datenerhalt |
| `test_personality_engine.py` | CRUD, Aktivierung, Schutz, Kompilierung (10 Achsen) |
| `test_communication_engine.py` | Moduswahl, Priorität, Override, Direktiven, Fail-soft |
| `test_companion_personality.py` | Zenji-Seed, Migration 2→3, Persistenz, Modell-Unabhängigkeit |
| `test_chat_modes.py` | Repräsentative Gespräche: Modi im echten Chatpfad |
| `test_policy_engine.py` | Sortierung, Konflikte, System-Schutz, Injection-Flags |
| `test_memory_engine.py` | Dedupe, Veralten/Konflikt, Suche, Merkwörter |
| `test_context_engine.py` | Budget, Abschnitte, Verlaufskürzung, Datenblöcke |
| `test_zenji_core.py` | Orchestrierung, Fallback ohne Core, Nachbereitung |
| `test_api_phase2.py` | Alle Endpunkte + Chat-Integration |

Der LLM ist gemockt (`FakeProvider`); Tests laufen ohne Netz, Modell
und geladene Gewichte (~1.4 s gesamt).

## Projektstruktur

```
ZENJI/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI-Fabrik + Lifespan (Migrationen, Engines)
│   │   ├── core/                 # config, exceptions, logging, storage, extensions
│   │   ├── api/routes/           # Phase 1 + personality, policies, memory, core
│   │   ├── engines/              # llm_engine, model_manager, providers/
│   │   │   ├── personality_engine.py   # Profile → Kontextblock
│   │   │   ├── policy_engine.py        # Regeln, Konflikte, Injection
│   │   │   ├── memory_engine.py        # Gedächtnis + Suche
│   │   │   └── context_engine.py       # Budget + Systemprompt-Compile
│   │   ├── services/             # chat_service, conversation_service,
│   │   │                         # settings_service, zenji_core
│   │   ├── database/             # database, models, migrations, repositories/
│   │   ├── config/               # personalities.json, system_policies.json
│   │   ├── schemas/              # Pydantic-API-Schemata (Phase 1 + 2)
│   │   └── interfaces/           # ABCs aller Engines
│   ├── tests/                    # pytest (178 Tests)
│   ├── requirements.txt          # getestete Versionen
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/           # Sidebar, ChatArea, Composer, SettingsPanel, …
│   │   ├── components/control/   # ControlCenter + Personality/Policies/Memory/Core-Tabs
│   │   ├── pages/ChatPage.tsx    # Layout
│   │   ├── hooks/                # useChat, useHealth, useConversations, useSettings,
│   │   │                         # usePersonalities, usePolicies, useMemories, useCoreStatus
│   │   ├── services/             # api.ts (REST), sse.ts (SSE-Parser)
│   │   ├── types/                # Spiegel der Backend-Schemata
│   │   └── styles/index.css      # Tailwind v4 Theme (Graphit + Jade)
│   └── package.json
├── docs/                         # ARCHITECTURE, API, DEVELOPMENT, STORAGE,
│                                 # PERSONALITY_ENGINE, POLICY_ENGINE,
│                                 # MEMORY_ENGINE, CONTEXT_ENGINE
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
- **Engines:** jede Engine implementiert `ZenjiEngine` (`interfaces/base.py`),
  wird im `ExtensionRegistry` registriert und arbeitet fail-soft. Der
  ZenjiCore orchestriert; der ChatService ruft Engines nie direkt.
- **Untrusted-Inhalte:** Chat-/Erinnerungs-/Webtexte sind Daten. Sie
  landen ausschließlich in `[INHALT_BEGINN]/[INHALT_ENDE]`-Blöcken und
  werden nie automatisch zu Regeln oder Profilfeldern.
- **Dependencies:** `requirements.txt` enthält die getesteten Pins; Änderungen
  nur mit erfolgreicher Testlauf-Bestätigung.

## Git

Das Projekt ist ein eigenständiges Git-Repository (`ZENJI/`). `node_modules`,
`.venv`, `dist`, Logs, Datenbanken und `.env` sind ignoriert (.gitignore).
