# ZENJI kostenlos online — Render (Backend) + Cloudflare Pages (Frontend)

Kompletter Betrieb **ohne einen Cent**: alle Bausteine sind Free-Pläne,
keine Kreditkarte nötig.

| Baustein | Anbieter | Plan | Kosten |
|---|---|---|---|
| Backend (FastAPI) | Render | Free (750 Instanz-Stunden/Monat) | 0 € |
| Seite (React/Vite) | Cloudflare Pages | Free | 0 € |
| Speicher, Accounts | Supabase | Free (Postgres + Auth) | 0 € |
| KI-Modell | Cloudflare Workers AI | Free (10.000 Neuronen/Tag) | 0 € |
| Internet-Recherche | DuckDuckGo | ohne Key | 0 € |
| Wachhalte-Dienst | UptimeRobot | Free (50 Monitore) | 0 € |

Der Render-Free-Plan schläft nach 15 Minuten ohne Traffic ein und wacht in
~1 Minute auf. 750 Stunden/Monat reichen exakt für einen 24/7-wachen Service
(744 h) — der UptimeRobot-Ping hält ihn wach, und selbst wenn der Ping
ausfällt, kostet Schlafen nichts.

## Schritt 1 — Backend auf Render (5 Minuten)

Voraussetzung: Repo `zenji` ist auf GitHub (privat). Die Datei `render.yaml`
im Repo-Root enthält die komplette Service-Definition.

1. https://dashboard.render.com → **New → Blueprint**
2. GitHub-Repo **zenji** auswählen und verbinden
3. Render zeigt die Variablen aus `render.yaml` mit `sync: false` als
   Formularfelder — die 5 Secrets eintragen (Werte stehen in `backend/.env`,
   dort 1:1 kopieren):

   | Variable | Wert (aus backend/.env) |
   |---|---|
   | `ZENJI_SUPABASE_URL` | `https://…supabase.co` |
   | `ZENJI_SUPABASE_ANON_KEY` | `sb_publishable_…` |
   | `ZENJI_SUPABASE_DB_URL` | Session-pooler-URL, siehe Hinweis unten |

> **Wichtig — Session-Pooler statt direkter DB-Adresse:** Die direkte
> Adresse (`db.<ref>.supabase.co:5432`) ist **IPv6-only** und scheitert auf
> Render mit „Network is unreachable". Nutze die IPv4-fähige
> Session-Pooler-URL aus **Supabase → Connect → Session pooler** —
> Format: `postgresql://postgres.<ref>:<pass>@aws-0-<region>.pooler.supabase.com:5432/postgres`
   | `ZENJI_CLOUDFLARE_ACCOUNT_ID` | 32-stellige Konto-ID |
   | `ZENJI_CLOUDFLARE_API_TOKEN` | Workers-AI-Token |

4. **Apply** → Build (~2–3 min) → Backend ist live unter
   `https://zenji-api.onrender.com`

Prüfen: `https://zenji-api.onrender.com/api/health` muss `"available": true`
für Modell **und** Datenbank melden.

## Schritt 2 — Frontend auf Cloudflare Pages

```bash
cd frontend
npm run build          # mit VITE_API_BASE_URL auf die Render-URL gesetzt
npx wrangler pages deploy dist --project-name zenji
```

`VITE_*`-Werte werden beim Build eingebacken; nach jedem Backend-URL-Wechsel
neu bauen und deployen. Ziel: `https://zenji-chm.pages.dev`

## Schritt 3 — Supabase-Redirects

Dashboard → Authentication → URL Configuration:

- Site URL: `https://zenji-chm.pages.dev`
- Redirect URLs: `https://zenji-chm.pages.dev/**`

## Schritt 4 — Wachhalten (UptimeRobot, 2 Klicks)

1. https://uptimerobot.com → kostenlosen Account anlegen
2. **Add New Monitor** → HTTP(s) → Name `zenji-api` →
   URL `https://zenji-api.onrender.com/api/health` → Intervall 5 min

Damit schläft das Backend nie ein und antwortet sofort.

## Verhalten & Grenzen (ehrlich)

- **Kaltstart:** Ohne Ping-Dienst dauert die erste Anfrage nach 15+ Minuten
  Pause ~1 Minute (Render zeigt eine Ladeseite).
- **Ephemerales Dateisystem:** Render verliert lokale Dateien bei Redeploys —
  irrelevant, da alle Daten in Supabase liegen (Cloud-Speicher-Modus).
- **Deploy:** Jeder `git push` auf GitHub triggert automatisch einen neuen
  Render-Deploy.
- **Suchanbieter:** In der Cloud wird DuckDuckGo genutzt (SearXNG läuft
  localhost-only). Die Einstellung ist eine globale DB-Einstellung — steht
  sie auf `searxng`, gilt sie auch für die Cloud-Instanz.
- **Free-Limits:** Render 750 h/Monat + 5 GB Traffic, Supabase Free-Plan,
  Workers AI 10.000 Neuronen/Tag — für persönliche Nutzung deutlich
  ausreichend.
- **Kein SMTP-Port 25/465/587:** Render blockt ausgehende Mail-Ports;
  ZENJI versendet selbst keine Mails (Passwort-Reset macht Supabase).
