# ZENJI – Roadmap (Empfehlungen für Phase 2+)

Stand: Abschluss Phase 1

## Sofort nach Phase 1 (ohne Neuentwicklung)

1. **SSD verbinden → `./scripts/setup.sh` → `./scripts/download_model.sh`**
   – danach läuft ZENJI produktiv mit qwen3:8b auf der SSD.
2. Erste echte Gesprächsprotokolle sammeln (nützlich für Persona-Tuning).

## Phase 2 – Persönlichkeit, Policy, Memory

- **PolicyEngine** (Schnittstelle steht in `app/interfaces/base.py`):
  Verhaltensrichtlinien als deklaratives Regelwerk (YAML), Prüfpunkte im
  ChatService sind vorbereitet (`registry.get("policy")`, fail-soft).
- **MemoryEngine**: Fakten-/Präferenzextraktion pro Nutzer; Einhängen in
  `_build_context` (geplanter Datenfluss ist im Code dokumentiert).
- **Persona-Profile**: mehrere Persönlichkeiten wählbar, Versionierung.

## Phase 2/3 – Erweiterungen

- **ToolEngine + WebEngine**: Tool-Calling-Schema über die Provider-
  Abstraktion (Ollama unterstützt `tools`); Web-Suche/Analyse als Tool.
- **RAGEngine**: Dokumentenanalyse (PDF/Markdown), Embeddings auf der SSD
  (`datasets/`), SQLite-Vektorapproach oder sqlite-vec.
- **PluginManager**: dynamisches Laden von Engines/Tools aus Verzeichnissen.
- **ImageEngine**: Bildverständnis (LLaVA/qwen-vl über Ollama) → später
  Generierung (eigener Provider).
- **Zusätzliche Provider**: llama.cpp / OpenAI-kompatible Endpunkte über
  `register_provider` – die Basis (ABC, Registry, Tests) steht.

## Technische Verbesserungen (Rückstand bewusst dokumentiert)

- **Kontextfenster-Management**: Verlauf jetzt per Nachrichtenanzahl (50)
  begrenzt; Phase 2: tokenbasiertes Fenster (Abzählen via `num_ctx`).
- **Migrationen**: Schema aktuell per `create_all`; bei Schemaänderungen
  Alembic einführen.
- **SSE-ServerEvents für Status**: Statusleiste pollet (8 s); später per
  SSE statt Polling.
- **Frontend**: virtueller Nachrichtenverlauf bei sehr langen Chats,
  Tastaturnavigation, i18n-Schicht (Strings zentralisieren).
- **Auth (optional)**: ZENJI bindet nur an localhost; fallsfern-Zugriff
  gewünscht wird, Token-Auth vor `/api/*` setzen.

## Betrieb

- Backups: `VACUUM INTO`-gestütztes Backup-Skript nach `<SSD>/backups/`.
- Logging-Rotation ist aktiv (2 MB × 3); Auswertung der Latenzen über
  `time_ms` im Health-Endpoint.
