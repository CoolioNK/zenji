# LLM-Provider: Cloudflare Workers AI

ZENJI ist provider-abstrahiert (`app/engines/providers/base.py`). Neben dem
lokalen Ollama-Server gibt es den Provider `cloudflare` für
**Cloudflare Workers AI** – KI-Modelle in der Cloudflare-Cloud, im Free-Plan
**kostenlos** (täglich 10.000 Neuronen, siehe
[Workers-AI-Preise](https://developers.cloudflare.com/workers-ai/platform/pricing/)).

Der aktive Provider ist eine **Nutzereinstellung** in `backend/.env`
(Bootstrap) – die API-Schnittstelle (Chat, Streaming, Recherche) verhält sich
beide Male identisch.

## Aktivierung (backend/.env)

```dotenv
ZENJI_LLM__PROVIDER=cloudflare
ZENJI_LLM__MODEL=@cf/meta/llama-3.1-8b-instruct-fast
ZENJI_CLOUDFLARE_ACCOUNT_ID=<32-stellige Konto-ID>
ZENJI_CLOUDFLARE_API_TOKEN=<API-Token mit Workers-AI-Run-Berechtigung>
```

Werte im Cloudflare-Dashboard:

- **Konto-ID**: Übersicht → rechts „Account ID" (32 Hexzeichen).
- **API-Token**: My Profile → API Tokens → Create Token
  (Berechtigung: Account → Workers AI → Run/Edit).

Rückwechsel zu Ollama: `ZENJI_LLM__PROVIDER=ollama` +
`ZENJI_LLM__MODEL=qwen3:8b`. Der lokale Ollama-Server bleibt unverändert
installiert und kann parallel weiterlaufen.

## Modellwahl

`ZENJI_LLM__MODEL` muss eine Workers-AI-Modell-ID mit `@cf/…`-Präfix sein.
Die chat-tauglichen Modelle des Katalogs listet `GET /api/models` auf
(Gefiltert auf „Text Generation"). Beispiele:

| Modell | Charakter |
|---|---|
| `@cf/meta/llama-3.1-8b-instruct-fp8` | sparsam (≈2 Neuronen/kurze Antwort), ideal für den Free-Plan |
| `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | deutlich stärker (≈8× Neuronen), gelistet |
| `@cf/qwen/qwen2.5-coder-32b-instruct` | code-fokussiert |

Hinweise (Stand Katalog-Prüfung 17.11.2026): Denk-Modelle wie
`@cf/qwen/qwen3-30b-a3b-fp8` funktionieren, verbrauchen aber Neuronen für
Reasoning-Ausgaben (mit `strip_think` ggf. leere sichtbare Antwort bei
kleinem `max_tokens`). Manche Modelle (z. B. `@cf/zai-org/glm-5.3-flash`)
sind nur im Bezahlplan verfügbar (HTTP 403 im Free-Plan).

## Architektur

- `app/engines/providers/cloudflare.py` – REST-Anbindung
  (`/ai/models/search`, `/ai/run/{model}`), Streaming via
  Server-Sent-Events (`data: {"response": …}` … `data: [DONE]`).
- `app/core/config.py` – `cloudflare_account_id` / `cloudflare_api_token`
  (flache `ZENJI_*`-Variablen) + `CloudflareDefaults` (Timeouts, `strip_think`).
- `app/engines/providers/__init__.py` – Factory-Registrierung
  (`create_provider("cloudflare", …)`).
- `app/main.py` – providerabhängige Konfigurationsübergabe.

Parameter-Abbildung: `num_predict` → `max_tokens`; `temperature`, `top_p`,
`stop` 1:1. Ollama-spezifische Parameter (`num_ctx`, `repeat_penalty`,
`top_k`, `keep_alive`, `think`) haben in Workers AI kein Pendant und werden
bewusst nicht gesendet.

## Verhalten im Störfall

ZENJI startet immer (fail-soft); `/api/health` und der Modell-Statusbericht
zeigen die Ursache in deutscher Sprache:

- **Zugangsdaten fehlen** → „Cloudflare Workers AI ist nicht konfiguriert:
  ZENJI_CLOUDFLARE_ACCOUNT_ID und ZENJI_CLOUDFLARE_API_TOKEN fehlt."
- **Token abgelehnt** (HTTP 401/403) → „Cloudflare hat den API-Token
  abgelehnt … Token prüfen." (Fehlercode `CLOUDFLARE_UNAVAILABLE`)
- **Unbekanntes Modell** (HTTP 404) → `MODEL_NOT_FOUND` mit Hinweis auf
  `ZENJI_LLM__MODEL`.
- **Free-Limit erreicht** (HTTP 429) → Hinweis auf die 10.000
  Neuronen/Tag-Grenze.

Tests: `backend/tests/test_providers_cloudflare.py` (23 Fälle, MockTransport,
kein echter Netzwerkzugriff).
