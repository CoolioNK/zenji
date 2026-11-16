# ZENJI – Architektur (Phase 1 + 2 + 3)

ZENJI ist ein **eigenständiges, modulares KI-System**. Das Sprachmodell ist
nur sein Generierungskern – Architektur, Steuerung, Persönlichkeit, Regeln,
Gedächtnis, Kontextverwaltung, Internet-Recherche und zukünftige
Erweiterungen gehören zum selbst entwickelten ZENJI-System.

**Leitprinzip (Phase 2):** Das Modell erzeugt Antworten. ZENJI entscheidet,
mit welcher Identität, welchen Regeln, welchen Erinnerungen und welchem
Kontext diese Antworten entstehen.

**Leitprinzip (Phase 3):** ZENJI recherchiert selbst, bewertet Quellen und
belegt Antworten nachvollziehbar – das Modell erfindet keine Belege.

## 1. Schichtenübersicht

```
┌────────────────────────────────────────────────────────────┐
│ Frontend (React + TypeScript + Vite + Tailwind)             │
│  Sidebar · Chat · Streaming (SSE) · Einstellungen · Status   │
│  Recherche-Steuerung + Live-Panel (Chat) · Tab „Web" (CC)    │
│  Control Center: Personality · Policies · Memory · Core · Web│
└──────────────────────────────┬─────────────────────────────┘
                               │ HTTP / SSE (/api/*)
┌──────────────────────────────▼─────────────────────────────┐
│ FastAPI (app/api/routes)                                    │
│  health · models · settings · conversations · chat          │
│  personality · policies · memory · core (Phase 2)           │
│  web · research · sources (Phase 3)                         │
├────────────────────────────────────────────────────────────┤
│ Services (app/services)                                     │
│  ChatService        Persistenz + LLM-Aufruf; Kontext kommt  │
│                     vom ZenjiCore (oder Phase-1-Fallback)    │
│  ConversationService CRUD für mehrere Chats                  │
│  SettingsService    Laufzeit-Konfiguration (DB ∪ Defaults)   │
│  ZenjiCore          Orchestrierung aller Engines (Phase 2)  │
│  WebIntelligenceService Fassade Recherche (Phase 3)         │
├────────────────────────────────────────────────────────────┤
│ Web Intelligence (app/web_intelligence, Phase 3)            │
│  search_engine      SearXNG/Brave, Normalisierung, Dedupe   │
│  browser_engine     httpx (+Playwright), robots, Host-Pause │
│  ssrf               URL/IP-Schutz, Redirect-Prüfung         │
│  content_extractor  trafilatura/BS4 → Text + Metadaten      │
│  source_manager     Registrierung, Snapshots, Dedupe        │
│  source_analysis    Quelltyp, Frische, Relevanz, Konflikte  │
│  citation_engine    Marker-Whitelist, erfundene Belege raus │
│  research_cache     Such-/Abruf-Cache mit TTL               │
│  research_planner   Bedarfserkennung, Pläne, Limits         │
│  research_engine    Orchestrator (Report, Live-Events)      │
├────────────────────────────────────────────────────────────┤
│ Engines (app/engines)                                       │
│  PersonalityEngine  Profile laden → Persönlichkeitskontext   │
│  CommunicationManager situativer Modus + Stilvorgabe (v0.3) │
│  PolicyEngine       Regeln priorisieren, Konflikte, Schutz   │
│  MemoryEngine       Gedächtnis: CRUD, Suche, Auswahl         │
│  ContextEngine      Token-Budget, Systemprompt-Compile       │
│  LLMEngine          Schlanke Fassade: nur Kommunikation      │
│  ModelManager       Verfügbarkeit, Infos, klare Fehler       │
│  providers/         Provider-Abstraktion (base.py)           │
│    └── OllamaProvider (Phase 1)                              │
│    └── weitere Provider in Phase 3+ registrierbar             │
├────────────────────────────────────────────────────────────┤
│ Datenbank (app/database)                                    │
│  Database (SQLite/WAL) · ConversationModel · MessageModel    │
│  SettingModel · PersonalityModel · PolicyModel · MemoryModel │
│  research_sessions · search_* · sources · snapshots ·        │
│  citations · research_cache (Phase 3)                        │
│  SchemaVersion · Repositories · Migrationen + Seeds          │
├────────────────────────────────────────────────────────────┤
│ Core (app/core)                                             │
│  config (Bootstrap) · settings-Validierung · logging         │
│  storage (SSD-Manager) · exceptions · extensions (Registry)  │
│  interfaces/ (ABCs aller Engines)                            │
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

## 3. Chat-Datenfluss (Phase 2 + v0.3.0 + v0.5.0)

```
Nutzer → POST /api/chat/stream
  1. preflight: Settings laden, Konversation prüfen, Modell prüfen
     → Fehler hier = saubere HTTP-Meldung (503/502/409/404)
  2. Nutzernachricht persistieren (eigene Transaktion, commit vor
     der Recherche – verhindert SQLite-Schreibkonflikte)
  3. ZENJI Core orchestriert (prepare_turn):
     a. Settings laden                      (SettingsService)
     b. Persönlichkeit laden + kompilieren  (PersonalityEngine)
     c. Kommunikationsmodus wählen          (CommunicationManager:
                                              Override → explizit → Signale
                                              → Standard; temporär, v0.3.0)
     d. Aktive Regeln kompilieren           (PolicyEngine, mit Konfliktreport)
     e. Relevante Erinnerungen suchen       (MemoryEngine, FTS5/LIKE)
     e2. Web-Recherche (v0.5.0, fail-soft):
         Modus normalisieren (auto/off/quick|standard|deep) →
         Bedarfserkennung (nur auto) → ResearchEngine.run
         mit Live-Ereignissen → Report + Kontext-Datenblock
     f. Verlauf laden                       (ConversationService, max. 50)
     g. Kontext bauen + Budget prüfen       (ContextEngine, ein Systemprompt;
                                             Recherche zwischen Erinnerungen
                                             und Verlauf als Datenblock)
     h. Injection-Prüfung der Anfrage       (PolicyEngine.check_incoming,
                                             fail-soft, nur Flags)
  4. LLMEngine.stream(...) → OllamaProvider → NDJSON → StreamChunk
  5. SSE-Ereignisse: start → research* (echte Recherche-Schritte) →
     delta* → done (oder error)
  6. Zitat-Validierung: CitationEngine entfernt erfundene [n]-Marker
     (Warnungen bleiben im done-Event sichtbar)
  7. Assistentennachricht persistieren (auch Teilantworten bei
     Abbruch/Fehlern – der Chatverlauf bleibt konsistent)
  8. ZENJI Core Nachbereitung (finalize_turn):
     Merkwörter speichern (source=chat) · last_used_at setzen
     (Recherche-Reports gehen NICHT automatisch ins Gedächtnis)
```

Nicht-streamender Pfad (`POST /api/chat`) nutzt dieselbe Logik mit
`generate()` statt `stream()`.

**Phase-1-Fallback:** Ohne injizierten Core verhält sich der ChatService
exakt wie in Phase 1 (Persona-Systemprompt + Verlauf + Anfrage). Der
Fallback ist bewusst erhalten – Tests und Notfallbetrieb hängen nicht am
Core. Alle Engines sind fail-soft: Ein Fehler in einem Schritt reduziert
den Kontext, blockiert aber nie die Antwort.

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

## 6. Engines (Phase 2 aktiv, v0.3.0 Begleiter, Phase 3+ Erweiterung)

Die Phase-2-Engines sind implementiert und im Chatpfad aktiv; v0.3.0 ergänzt
den CommunicationManager:

| Engine | Modul | Dokumentation |
|---|---|---|
| `PersonalityEngine` | `app/engines/personality_engine.py` | **PERSONALITY_ENGINE.md** |
| `CommunicationManager` | `app/engines/communication_engine.py` | **COMMUNICATION_MODES.md** |
| `PolicyEngine` | `app/engines/policy_engine.py` | **POLICY_ENGINE.md** |
| `MemoryEngine` | `app/engines/memory_engine.py` | **MEMORY_ENGINE.md** |
| `ContextEngine` | `app/engines/context_engine.py` | **CONTEXT_ENGINE.md** |
| `ZenjiCore` (Orchestrierung) | `app/services/zenji_core.py` | ARCHITECTURE.md, §3 |
| `WebIntelligenceService` (Fassade) | `app/services/web_intelligence_service.py` | **WEB_INTELLIGENCE.md** |

Phase-3-Komponenten (`app/web_intelligence/`): search_engine, browser_engine,
ssrf, content_extractor, source_manager, source_analysis, citation_engine,
research_cache, research_planner, research_engine – Dokumentation:
**SEARCH_ENGINE.md**, **BROWSER_ENGINE.md**, **RESEARCH_ENGINE.md**,
**SOURCE_MANAGEMENT.md**, **CITATION_SYSTEM.md**, **WEB_SECURITY.md**.

Weitere zukünftige Engines (Phase 3+):

| Engine | Zweck | Registrierung |
|---|---|---|
| `WebEngine` | Websuche, Website-Analyse | `registry.register(engine)` |
| `ToolEngine` | Tool Calling (Deklaration + Ausführung) | wie oben |
| `PluginManager` | dynamische Erweiterungen | wie oben |
| `RAGEngine` | Dokumentenanalyse/Retrieval | wie oben |
| `ImageEngine` | Bildverständnis/-generierung | wie oben |
| `EmbeddingSearchProvider` | semantische Suche fürs Gedächtnis | MemoryEngine |

Alle Engines stehen im `ExtensionRegistry` (fail-soft für Abfragestellen)
und implementieren das `ZenjiEngine`-Protokoll aus `app/interfaces/base.py`.

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
| PERSONALITY_NOT_FOUND | 404 | Unbekanntes Persönlichkeitsprofil |
| PERSONALITY_PROTECTED | 409 | System-/aktives Profil ist geschützt |
| PERSONALITY_NAME_TAKEN | 409 | Profilname bereits vergeben |
| POLICY_NOT_FOUND | 404 | Unbekannte Regel |
| POLICY_SYSTEM_PROTECTED | 403 | Systemregel nicht änderbar/löschbar |
| POLICY_ID_TAKEN | 409 | Regel-ID bereits vergeben |
| MEMORY_NOT_FOUND | 404 | Unbekannte Erinnerung |
| VALIDATION_ERROR | 422 | Ungültige Anfrage/Einstellung |
| WEB_SECURITY_BLOCKED | 403 | Abruf abgelehnt (private Adresse, robots) |
| SEARCH_PROVIDER_UNAVAILABLE | 502 | Suchanbieter nicht erreichbar |
| WEB_FETCH_FAILED | 502 | Seitenabruf fehlgeschlagen |
| WEB_INTELLIGENCE_ERROR | 502 | Allgemeiner Web-Intelligence-Fehler |
| RESEARCH_NOT_FOUND | 404 | Unbekannte Recherche-Session |
| SOURCE_NOT_FOUND | 404 | Unbekannte Quelle |
| INTERNAL_ERROR | 500 | Unerwarteter Fehler (geloggt) |

## 8. Engine-Dokumentation

Datenflüsse und Zusammenspiel der Engines (Phase 2 + v0.3.0):

- **PERSONALITY_ENGINE.md** – Profile, Kompilierung, Aktivierung
- **COMMUNICATION_MODES.md** – situative Modi, Moduswahl, manuelle Anfrage
- **POLICY_ENGINE.md** – Prioritäten, Konflikte, System-Schutz, Injection
- **MEMORY_ENGINE.md** – Typen, Suche, Duplikate, Veralten, Merkwörter
- **CONTEXT_ENGINE.md** – Token-Budget, Systemprompt-Compile, Nachvollziehbarkeit
- **WEB_INTELLIGENCE.md** – Phase 3 Überblick: Moduse, Datenfluss, Konfiguration
- **SEARCH_ENGINE.md** – Suchanbieter, Normalisierung, Dedupe
- **BROWSER_ENGINE.md** – Abrufe, robots.txt, SSRF, Playwright-Fallback
- **RESEARCH_ENGINE.md** – Planner, Orchestrator, Report, Live-Events
- **SOURCE_MANAGEMENT.md** – Quellen, Snapshots, Bewertung, Konflikte
- **CITATION_SYSTEM.md** – Marker-Whitelist, erfundene Belege entfernen
- **WEB_SECURITY.md** – SSRF, Geheimnisse, Ehrlichkeit, Nutzerkontrolle
