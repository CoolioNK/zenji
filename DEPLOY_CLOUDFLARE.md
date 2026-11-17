# Cloudflare Pages – ZENJI Frontend

Statisches Vite/React-Bundle. Das Backend läuft separat als FastAPI-Service
(Workers/VPS/Container) und wird über `VITE_API_BASE_URL` oder den optionalen
Pages-Proxy `functions/api/[[path]].ts` angebunden.

## Build

```bash
cd frontend
npm ci
npm run build
```

Pages-Konfiguration:

- Build command: `npm run build`
- Build output directory: `dist`
- Root directory: `frontend` (falls Pages auf das Repo zeigt)
- Node version: 22

## Environment (Pages → Settings → Environment variables)

Produktiv:

```env
VITE_SUPABASE_URL=https://<ref>.supabase.co
VITE_SUPABASE_ANON_KEY=<publishable key>
VITE_API_BASE_URL=https://<backend-origin>
VITE_PUBLIC_APP_URL=https://<project>.pages.dev
```

Optionaler Same-Origin-Proxy statt `VITE_API_BASE_URL`:

```env
API_ORIGIN=https://<backend-origin>
ALLOWED_ORIGIN=https://<project>.pages.dev
```

`ALLOWED_ORIGIN` ist nur nötig, wenn der Proxy CORS-Antworten für Cross-Origin-
Browser ausliefern soll. Bei rein same-origin Aufrufen kann es leer bleiben.

## Backend-CORS

Das Backend muss die Pages-Origin erlauben:

```env
ZENJI_PUBLIC_BASE_URL=https://<project>.pages.dev
ZENJI_CORS_ORIGINS=https://<project>.pages.dev
```

`ZENJI_PUBLIC_BASE_URL` wird automatisch zu den erlaubten CORS-Origins addiert.

## Supabase Auth

Unter **Authentication → URL Configuration**:

- Site URL: `https://<project>.pages.dev`
- Redirect URLs: `https://<project>.pages.dev/**`

Für Passwort-Reset wird `VITE_PUBLIC_APP_URL` als Redirect verwendet. Die
Supabase-E-Mail-Templates müssen auf dieselbe Domain zeigen.

## Vor dem Launch prüfen

- `VITE_SUPABASE_*` und `VITE_API_BASE_URL` sind in der richtigen Pages-Umgebung gesetzt.
- `ZENJI_CORS_ORIGINS` enthält die Pages-Origin.
- Backend-Health ist öffentlich erreichbar: `GET /api/health`.
- Login/Registrierung und ein Streaming-Chat funktionieren auf der Pages-Domain.
- Keine Secrets (`service_role`, DB-URL, JWT-Secret) im Frontend.

## Hinweise

- `functions/api/[[path]].ts` ist optional. Es leitet `/api/*` an `API_ORIGIN`
  weiter und hält SSE-Streaming unverändert durch.
- Das Backend bleibt zuständig für Auth, RLS, Datenbank und Modell-Inferenz.
- Cloudflare Pages ist kein Backend-Host für den aktuellen Python-FastAPI-Code.