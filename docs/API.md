# ZENJI API (Phase 1 + 2)

Basis: `http://localhost:8000` · Alle Antworten JSON (UTF-8).
Fehlerformat einheitlich:

```json
{ "error": { "code": "MODEL_NOT_FOUND", "message": "…", "detail": {} } }
```

Interaktive Doku (Swagger UI): `http://localhost:8000/docs`

---

## GET /api/health

Gesamtstatus für die Statusleiste. **Antwortet immer HTTP 200**, auch im
gestörten Zustand (`status: "degraded"`).

```json
{
  "status": "ok",
  "version": "0.1.0",
  "time_ms": 6.0,
  "storage":   { "available": true,  "root": "/Volumes/ZENJI-SSD", "message": "…" },
  "database":  { "ok": true, "path": "…/zenji.db", "message": "…" },
  "ollama":    { "available": true, "version": "0.40.16", "base_url": "…", "message": "" },
  "model":     { "model": "qwen3:8b", "available": false, "message": "…" }
}
```

## GET /api/models

Verfügbare Modelle beim aktiven Provider + aktives Modell.
Bei ausgefallenem Provider: HTTP 200 mit `available: false` und Meldung.

```json
{
  "provider": "ollama",
  "available": true,
  "active_model": "qwen3:8b",
  "models": [
    { "name": "qwen3:8b", "family": "qwen3", "parameter_size": "8.2B",
      "quantization": "Q4_K_M", "size_bytes": 5100000000, "modified_at": "…" }
  ]
}
```

## GET /api/settings

Effektive Einstellungen (Laufzeit-DB + Bootstrap-Defaults).

```json
{
  "llm": { "provider": "ollama", "model": "qwen3:8b", "temperature": 0.7,
           "top_p": 0.9, "top_k": 20, "repeat_penalty": 1.05,
           "num_predict": 2048, "num_ctx": 8192, "stream": true },
  "providers": { "ollama": { "base_url": "http://localhost:11434",
                  "timeout": 120.0, "connect_timeout": 5.0,
                  "keep_alive": "10m", "think": false, "strip_think": true } },
  "persona": { "system_prompt": "Du bist ZENJI …" }
}
```

## PATCH /api/settings

Teilweise Änderung, Deep-Merge je Gruppe; validiert, persistent.

```json
{ "llm": { "temperature": 0.55 },
  "providers": { "ollama": { "timeout": 60 } },
  "persona": { "system_prompt": "…" } }
```

- `200` → vollständige aktualisierte Einstellungen
- `422` → ungültige Werte (mit Feldhinweis)
- `503` → SSD/Datenbank nicht verfügbar

## GET /api/conversations

Liste (neueste zuerst): `[{ id, title, created_at, updated_at, message_count }]`

## POST /api/conversations

Body: `{"title": "optional"}` → `201` mit vollständiger Konversation.

## GET /api/conversations/{id}

Konversation inkl. `messages: [ {id, conversation_id, role, content, created_at} ]`.
`404 CONVERSATION_NOT_FOUND` bei unbekannter ID.

## PATCH /api/conversations/{id}

Umbenennen: `{"title": "Neuer Titel"}` → `200`.

## DELETE /api/conversations/{id}

Löscht Konversation **und** Nachrichten (Kaskade) → `204`.

---

## POST /api/chat

Nicht-streamend. Body: `{"conversation_id": "optional", "message": "…", "mode": "optional"}`.
Ohne `conversation_id` wird automatisch eine Konversation angelegt
(Titel = Anfang der ersten Nachricht). `mode` erzwingt einen
Kommunikationsmodus (`casual|roast|focus|empathy|open_talk`, v0.3.0); ohne
`mode` wählt der CommunicationManager automatisch (siehe
**COMMUNICATION_MODES.md**). Unbekannter Modus → `422`.

```json
{
  "conversation_id": "…",
  "user_message":      { "id": "…", "role": "user",      "content": "…", "created_at": "…" },
  "assistant_message": { "id": "…", "role": "assistant", "content": "…", "created_at": "…" }
}
```

Fehler: `502` Ollama down · `409` Modell fehlt · `503` SSD fehlt · `404` Konversation unbekannt · `422` Validierung.

## POST /api/chat/stream

Streaming über **Server-Sent Events** (`Content-Type: text/event-stream`).
Body wie `/api/chat`.

Eventfolge:

```
event: start
data: {"conversation_id": "…", "user_message_id": "…", "assistant_message_id": null}

event: delta
data: {"content": "Antwortteil "}

event: done
data: {"conversation_id": "…", "assistant_message_id": "…", "content": "vollständiger Text"}
```

Bei Fehlern **im** Stream: `event: error` mit `{code, message}`. Bereits
gestreamte Teilantworten werden gespeichert. Fehler **vor** dem Stream
(SSD, Ollama, Modell, Konversation) enden als HTTP-Statuscode mit dem
einheitlichen Fehlerformat – das Frontend zeigt sie sofort an.

Client-Hinweise: `Cache-Control: no-cache`, kein Puffern
(`X-Accel-Buffering: no`). Abbruch der Client-Verbindung stoppt die
Generierung; die Teilantwort bleibt im Verlauf erhalten.

Der Chatpfad nutzt in Phase 2 die volle Orchestrierung (ZenjiCore:
Persönlichkeit + Regeln + Erinnerungen + Kontext-Budget). Merkwörter
wie „Merke dir: …" erzeugen nach der Antwort Erinnerungen.

---

# Phase 2: Control Center

## Persönlichkeit (/api/personality)

### GET /api/personality
Alle Profile, aktives zuerst:

```json
[{
  "id": "…", "name": "Zenji", "identity": "Du bist ZENJI …",
  "base_personality": "friendly", "communication_style": "locker, frech …",
  "formality": 0.15, "humor": 0.9, "sarcasm": 0.65, "cheekiness": 0.75,
  "directness": 0.95, "friendliness": 0.9, "empathy": 0.85,
  "curiosity": 0.9, "initiative": 0.85, "creativity": 0.8,
  "response_length": "balanced", "language": "auto",
  "situational_behavior": {"Fehler oder Unsicherheit": "…"},
  "is_system": true, "is_active": true,
  "created_at": "…", "updated_at": "…"
}]
```

### POST /api/personality · 201
Nutzerprofil anlegen. Felder wie oben; Defaults: `base_personality=custom`,
Skalare 0.2–0.6, `response_length=balanced`, `language=auto`.
Fehler: `409 PERSONALITY_NAME_TAKEN` · `422 VALIDATION_ERROR`
(unbekannte Felder werden abgewiesen).

### PATCH /api/personality/{id} · 200
Teilweise Änderung (alle Felder optional). `is_active: true` aktiviert
das Profil (genau ein aktives).

### POST /api/personality/{id}/activate · 200
Aktivieren; deaktiviert alle anderen Profile.

### GET /api/personality/{id}/preview
Kompilierter Kontextblock: `{name, is_active, compiled_text}`.

### DELETE /api/personality/{id} · 204
Fehler: `409 PERSONALITY_PROTECTED` (Systemprofil oder aktives Profil).

## Regeln (/api/policies)

### GET /api/policies
Regelliste inkl. Konfliktbericht und Zähler:

```json
{
  "policies": [{
    "id": "zenji_identity", "name": "ZENJI-Identität",
    "instruction": "Du bist ZENJI …", "priority": 100,
    "enabled": true, "category": "identität", "scope": "global",
    "source": "system", "created_at": "…", "updated_at": "…"
  }],
  "conflicts": [{
    "winner_id": "…", "winner_name": "Kurzhalten B",
    "dropped_id": "…", "dropped_name": "Kurzhalten A",
    "similarity": 0.99, "reason": "…"
  }],
  "disabled_count": 0
}
```

### POST /api/policies · 201
Nutzerregel anlegen: `{name, instruction, priority=50, enabled=true,
category="stil", scope="global"}`. `id` optional (sonst ASCII-Slug aus
Name). `source` ist **nicht** setzbar (422) – Systemregeln entstehen nur
durch Seeds. Fehler: `409 POLICY_ID_TAKEN`.

### PATCH /api/policies/{id} · 200
Nutzerregel ändern (alle Felder optional, `priority` wird auf 0–100 geklemmt).
Fehler: `403 POLICY_SYSTEM_PROTECTED` bei Systemregeln · `404 POLICY_NOT_FOUND`.

### DELETE /api/policies/{id} · 204
Fehler: `403 POLICY_SYSTEM_PROTECTED` · `404 POLICY_NOT_FOUND`.

## Gedächtnis (/api/memory)

### GET /api/memory
Erinnerungen (neueste zuerst) + Zähler. Query-Parameter:
`memory_type` (conversation|long_term|preference|project), `category`,
`status` (active|superseded|archived, Default `active`), `limit` (1–500).

```json
{
  "memories": [{
    "id": "…", "content": "Der Nutzer heißt Max.", "category": "identität",
    "memory_type": "preference", "source": "chat", "source_ref": "conv-…",
    "relevance": 0.8, "status": "active", "supersedes_id": null,
    "last_used_at": null, "created_at": "…", "updated_at": "…"
  }],
  "stats": { "total": 3, "active": 2, "superseded": 1, "archived": 0,
             "by_type": {"preference": 2}, "categories": [["identität", 2]],
             "search_provider": "fts5" }
}
```

### POST /api/memory · 201
Anlegen: `{content, category="allgemein", memory_type="long_term",
relevance=0.5}`. Quelle ist immer `user`. Exakte Duplikate werden
zusammengeführt (aktualisierte bestehende Erinnerung, `merged`-Verhalten
intern). Fehler: `422` bei leerem Inhalt/ungültigem Typ/Relevanz außerhalb 0–1.

### POST /api/memory/search
```json
{ "query": "Python FastAPI", "memory_type": null, "category": null, "limit": 20 }
```
→ `[{ "memory": {…}, "score": 0.73 }]` (FTS5/LIKE, nur aktive Erinnerungen).

### GET /api/memory/{id}
Einzelabruf; `404 MEMORY_NOT_FOUND` bei unbekannter ID.

### PATCH /api/memory/{id} · 200
Änderbar: `content`, `category`, `memory_type`, `relevance`, `status`
(active|superseded|archived – Archivieren/Löschen ist Nutzerentscheidung).

### DELETE /api/memory/{id} · 204
Löscht Erinnerung **und** FTS-Index-Eintrag endgültig.

## Kern (/api/core)

### GET /api/core/status
Zentrale Zustände für das Control Center:

```json
{
  "version": "0.3.0",
  "personality": "Zenji", "personality_id": "…",
  "active_policies": 8, "policy_conflicts": 0,
  "memories": { "total": 3, "active": 2, "superseded": 1, "archived": 0,
                "by_type": {}, "search_provider": "fts5" },
  "model": "qwen3:8b", "provider": "ollama",
  "num_ctx": 8192, "num_predict": 2048,
  "communication_modes": [
    { "key": "casual", "label": "Casual" }, { "key": "roast", "label": "Roast" },
    { "key": "focus", "label": "Fokus" }, { "key": "empathy", "label": "Empathie" },
    { "key": "open_talk", "label": "Open Talk" }
  ],
  "communication_default_mode": "casual"
}
```

### GET /api/core/context-preview
Nachvollziehbarer Kontext-Entwurf **ohne LLM-Aufruf**. Query:
`message` (Default „Was kannst du?"), `conversation_id` (optional – mit
Verlauf aus dieser Konversation), `mode` (optional – erzwingt einen
Kommunikationsmodus im Entwurf).

```json
{
  "mode": "casual",
  "sections": [ { "key": "identity", "title": "identity", "tokens_est": 58,
                  "included": true, "truncated": false, "detail": "" }, … ],
  "budget_tokens": 5888, "used_tokens": 812, "usage_ratio": 0.138,
  "history_kept": 4, "history_dropped": 2,
  "memories_kept": 2, "memories_dropped": 0, "conflicts": 1,
  "flags": [],
  "system_text": "## Identität\n…",
  "messages": [ { "role": "system", "content": "…(gekürzt)", "chars": 2310 } ],
  "used_memory_ids": ["…"]
}
```

Damit ist jede Anfrage vollständig erklärenbar: welche Abschnitte,
wie viele Tokens, welche Erinnerungen im Kontext waren.
