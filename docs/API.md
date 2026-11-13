# ZENJI API (Phase 1)

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

Nicht-streamend. Body: `{"conversation_id": "optional", "message": "…"}`.
Ohne `conversation_id` wird automatisch eine Konversation angelegt
(Titel = Anfang der ersten Nachricht).

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
