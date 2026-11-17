# ZENJI mit Supabase (Accounts + Cloud-Speicher)

ZENJI kann vollständig mit Supabase laufen:

- **Accounts** über Supabase Auth (E-Mail + Passwort, ohne E-Mail-Bestätigung).
- **Alle Nutzerdaten** (Chats, Nachrichten, Einstellungen, Gedächtnis,
  Persönlichkeiten, Regeln, Recherche, Quellen) in Supabase Postgres.
- **Trennung der Nutzer** durch Row-Level-Security (RLS): Jeder Account sieht
  ausschließlich seine eigenen Zeilen.

## 1. Supabase-Projekt vorbereiten

1. Neues Projekt unter <https://supabase.com> anlegen.
2. **Authentication → Providers → Email** aktivieren.
3. **Authentication → Email Templates / Settings**:
   „Confirm email" **deaktivieren**, damit die Registrierung ohne
   E-Mail-Bestätigung direkt einloggt.
4. Zugangsdaten kopieren (Project Settings → API):
   - `Project URL`
   - **Publishable** Key (`sb_publishable_…`, früher „anon public") – für
     Frontend und Backend
   - **Secret** / `service_role` Key (`sb_secret_…`) – nur serverseitig, nie im
     Browser
5. Direkte Postgres-URL kopieren (Project Settings → Database → Connection
   string → URI).  Sie sieht so aus:
   `postgresql://postgres.<ref>:<pass>@aws-0-<region>.pooler.supabase.com:5432/postgres`

## 2. Konfiguration eintragen

### Backend (`backend/.env`)

```env
ZENJI_SUPABASE_URL=https://<ref>.supabase.co
ZENJI_SUPABASE_ANON_KEY=<anon public key>
ZENJI_SUPABASE_SERVICE_ROLE_KEY=<service_role key>
ZENJI_SUPABASE_DB_URL=postgresql://postgres.<ref>:<pass>@aws-0-<region>.pooler.supabase.com:5432/postgres
ZENJI_SUPABASE_JWT_SECRET=<optional>
```

### Frontend (`frontend/.env`)

```env
VITE_SUPABASE_URL=https://<ref>.supabase.co
VITE_SUPABASE_ANON_KEY=<anon public key>
```

Die `service_role`- und DB-Keys gehören **nur** ins Backend, niemals ins
Frontend.

## 3. Starten

```bash
# Backend
cd backend && ../.venv/bin/uvicorn app.main:app --port 8000

# Frontend ( zweites Terminal )
cd frontend && npm install && npm run dev
```

Beim ersten Backend-Start werden Tabellen **und** RLS-Policies automatisch
angelegt.  Optional kann `supabase/setup.sql` im Supabase-SQL-Editor
ausgeführt werden (idempotent).

Beim ersten Login wird pro Nutzer automatisch ein Profil sowie die
Standard-Persönlichkeiten und -Regeln angelegt.

## 4. Wie die Trennung funktioniert

1. Das Frontend meldet sich bei Supabase an und schickt den Access-Token als
   `Authorization: Bearer <token>` an das Backend.
2. Das Backend verifiziert den Token über die Supabase-Auth-API.
3. Pro Datenbank-Transaktion setzt das Backend
   `request.jwt.claims` auf die Nutzer-ID und wechselt in die Rolle
   `authenticated`.
4. Postgres-RLS verhindert dann **jeden** Zugriff auf Zeilen anderer Nutzer –
   auch bei vergessenen Filtern im Code.

## 5. Lokaler Modus (ohne Supabase)

Sind die Supabase-Variablen leer, läuft ZENJI wie bisher lokal mit SQLite
(Single-User, kein Login).  Das ist für Entwicklung/Tests gedacht; im
Produktivbetrieb sollten die Supabase-Variablen gesetzt sein.