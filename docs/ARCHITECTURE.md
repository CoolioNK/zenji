# ZENJI – Architektur (Phase 1)

ZENJI ist ein **eigenständiges, modulares KI-System**. Das Sprachmodell ist
nur sein Denk-Kern – Architektur, Steuerung, Persönlichkeit, Parameter-
verwaltung und zukünftige Erweiterungen gehören zum selbst entwickelten
ZENJI-System.

## 1. Schichtenübersicht

```
┌────────────────────────────────────────────────────────────┐
│ Frontend (React + TypeScript + Vite + Tailwind)             │
│  Sidebar · Chat · Streaming (SSE) · Einstellungen · Status   │
└──────────────────────────────┬─────────────────────────────┘
                               │ HTTP / SSE (/api/*)
┌──────────────────────────────▼─────────────────────────────┐
│ FastAPI (app/api/routes)                                    │
│  health · models · settings · conversations · chat          │
├────────────────────────────────────────────────────────────┤
│ Services (app/services)                                     │
│  ChatService        Orchestriert Konversation + Kontext +   │
│                     Engine; persistiert Nachrichten          │
│  ConversationService CRUD für mehrere Chats                  │
│  SettingsService    Laufzeit-Konfiguration (DB ∪ Defaults)   │
├────────────────────────────────────────────────────────────┤
│ Engines (app/engines)                                       │
│  LLMEngine          Schlanke Fassade: nur Kommunikation      │
│  ModelManager       Verfügbarkeit, Infos, klare Fehler       │
│  providers/         Provider-Abstraktion (base.py)           │
│    └── OllamaProvider (Phase 1)                              │
│    └── weitere Provider in Phase 2+ registrierbar             │
├────────────────────────────────────────────────────────────┤
│ Datenbank (app/database)                                    │
│  Database (SQLite/WAL) · ConversationModel · MessageModel    │
│  SettingModel · Repositories                                 │
├────────────────────────────────────────────────────────────┤
│ Core (app/core)                                             │
│  config (Bootstrap) · settings-Validierung · logging         │
│  storage (SSD-Manager) · exceptions · extensions (Registry)  │
│  interfaces/ (ABCs für Phase-2-Engines, noch nicht aktiv)    │
└────────────────────────────────────────────────────────────┘
```

## 2. Verantwortungstrennung (Grundregel)

- **LLMEngine/Provider**: ausschließlich Kommunikation mit dem Modell.
  Keine UI-Logik, keine Datenbanklogik, keine Policy-Entscheidungen.
- **ChatService**: entscheidet *was* gefragt wird (Kontextaufbau,
  Persistenz, Persona) – nicht *wie* die Antwort entsteht.
- **Provider-Abstraktion**: Ollama ist austauschbar. Neue Anbieter
  implementieren `LLMProvider` (in `app/engines/providers/base.py`) und
  registrieren sich in `app/engines/providers/__init__.py`.

## 3. Chat-Datenfluss

```
Nutzer → POST /api/chat/stream
  1. preflight: Settings laden, Konversation prüfen, Modell prüfen
     → Fehler hier = saubere HTTP-Meldung (503/502/409/404)
  2. Nutzernachricht persistieren
  3. Kontext: Persona-Systemprompt + Verlauf (max. 50) + Anfrage
     (Erweiterungspunkt Phase 2: MemoryEngine ergänzt hier Kontexte)
  4. LLMEngine.stream(...) → OllamaProvider → NDJSON → StreamChunk
  5. SSE-Ereignisse: start → delta* → done (oder error)
  6. Assistentennachricht persistieren (auch Teilantworten bei
     Abbruch/Fehlern – der Chatverlauf bleibt konsistent)
```

Nicht-streamender Pfad (`POST /api/chat`) nutzt dieselbe Logik mit
`generate()` statt `stream()`.

## 4. Konfiguration (zwei Ebenen)

| Ebene | Quelle | Änderbar über |
|---|---|---|
| Bootstrap | `ZENJI_*`-Umgebungsvariablen / `backend/.env` | Datei |
| Laufzeit | SQLite-Tabelle `settings` (JSON je Gruppe) | `PATCH /api/settings` |

Effektive Werte = Bootstrap-Defaults ∪ gespeicherte Änderungen.
Gruppen: `llm` (allgemein), `providers.ollama` (provider-spezifisch),
`persona` (Persönlichkeit). Validierung über Pydantic-Feldbereiche.

## 5. Speicherarchitektur

Alles liegt auf der externen SSD (`ZENJI_SSD_ROOT`, Standard
`/Volumes/ZENJI-SSD`): Projektcode, venv, Datenbank, Logs, Modellgewichte
(`OLLAMA_MODELS`). Details: **docs/STORAGE.md**.

Fehlerstrategie: fehlt die SSD, startet ZENJI trotzdem (nur der Chat-/DB-
Pfad liefert `503 STORAGE_UNAVAILABLE`) – das Frontend zeigt verständliche
Statusmeldungen, ein Crash wird verhindert. Ein SSD-Trennen während des
Betriebs wird über Schreibfehler erkannt und in `StorageUnavailableError`
übersetzt.

## 6. Erweiterungspunkte (Phase 2+)

`app/interfaces/base.py` definiert stabile ABCs; `app/core/extensions.py`
enthält die Registry:

| Engine | Zweck | Registrierung |
|---|---|---|
| `PolicyEngine` | Verhaltensrichtlinien prüfen (in/out) | `registry.register(engine)` |
| `MemoryEngine` | Langzeitgedächtnis, Kontextanreicherung | wie oben |
| `WebEngine` | Websuche, Website-Analyse | wie oben |
| `ToolEngine` | Tool Calling (Deklaration + Ausführung) | wie oben |
| `PluginManager` | dynamische Erweiterungen | wie oben |
| `RAGEngine` | Dokumentenanalyse/Retrieval | wie oben |
| `ImageEngine` | Bildverständnis/-generierung | wie oben |

Der ChatService fragt Engines **fail-soft** ab (`registry.get("policy")`):
in Phase 1 ist keine registriert, das Verhalten ist identisch. Phase 2 kann
Engine für Engine aktivieren, ohne den Chat-Pfad umzubauen.

## 7. Fehlerbehandlung

Einheitliches Format `{"error": {"code", "message", "detail"}}`.

| Code | HTTP | Bedeutung |
|---|---|---|
| STORAGE_UNAVAILABLE | 503 | SSD fehlt/getrennt/nicht beschreibbar |
| DATABASE_ERROR | 503 | SQLite-Fehler (nicht SSD-bedingt) |
| OLLAMA_UNAVAILABLE | 502 | Provider nicht erreichbar |
| LLM_TIMEOUT | 504 | Modell antwortet nicht rechtzeitig |
| LLM_RESPONSE_ERROR | 502 | Ungültige Provider-Antwort |
| MODEL_NOT_FOUND | 409 | Modell nicht geladen (mit Pull-Hinweis) |
| CONVERSATION_NOT_FOUND | 404 | Unbekannte Konversation |
| VALIDATION_ERROR | 422 | Ungültige Anfrage/Einstellung |
| INTERNAL_ERROR | 500 | Unerwarteter Fehler (geloggt) |
