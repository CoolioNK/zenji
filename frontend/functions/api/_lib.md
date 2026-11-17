# /api/*

This optional Pages Function proxies API calls to the ZENJI FastAPI backend.
It is only used when `VITE_API_BASE_URL` is empty. If the frontend targets an
external API origin, delete this file or keep it as a same-origin fallback.

Configuration:
- `API_ORIGIN`: full backend origin, e.g. `https://zenji-api.example.workers.dev`
- `ALLOWED_ORIGIN`: optional explicit frontend origin for CORS

The backend must allow this Pages origin via `ZENJI_CORS_ORIGINS`.

```bash
wrangler pages secret put API_ORIGIN --project-name zenji
# optional:
wrangler pages secret put ALLOWED_ORIGIN --project-name zenji
```