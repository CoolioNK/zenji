# Web Security (Sicherheit & Selbstbestimmung, v0.5.0)

Internet-Recherche öffnet ein System nach außen. ZENJI tut das mit
engeren Grenzen, ehrlichen Meldungen und voller Nutzerkontrolle.

## 1. SSRF-Schutz (`ssrf.py`)

- `check_url(url, resolver)`: nur `http(s)`, Host-Auflösung, **Ablehnung**
  privater/looperAdapter/bekannt interner IPs (localhost, 10/8, 172.16/12,
  192.168/16, 169.254/16, ::1, fdc/dok …), IP-Literale direkt geprüft.
- `check_redirect`: jeder Redirect-Hop wird neu geprüft – kein Umgehen
  über Umleitungen.
- Fehlerart: `WebSecurityError` (klar benannt, z. B. „private Adresse
  blockiert“).

## 2. Robots & Höflichkeit

- robots.txt wird pro Host geladen, gecacht und **respektiert**
  (`robots_respected: true` im Status). Blockierte Seiten erscheinen im
  Report (`blocked`), werden nicht umgangen.
- Host-Pause: min. Abstand zwischen Abrufen desselben Hosts
  (`per_host_delay_s`, Default 1) – kein Fluten fremder Server.
- Timeouts und Redirect-Limits begrenzen jeden Abruf.

## 3. Injection-Sicherheit (Kontext)

Recherche-Inhalte sind **Daten, niemals Anweisungen**: Die ContextEngine
bettet den Block in `[INHALT_BEGINN]`/`[INHALT_ENDE]` ein und der
Systemtext erklärt die Behandlung strikt als Information. Zusammen mit der
bestehenden Injection-Erkennung der Policy Engine gilt das auch für
Inhalte von Webseiten („Ignoriere alle Regeln“ auf einer fremden Seite ist
ein Text, kein Befehl an ZENJI).

## 4. Geheimnisse

- `brave_api_key` steht nur in der Einstellungsgruppe `web_intelligence`
  (DB). `GET /api/web/settings` gibt ihn **nie** zurück – nur
  `brave_api_key_set: true|false`.
- Kein Schlüssel in Logs, Fehlern oder Statusberichten.

## 5. Ehrlichkeit statt Fake

- Status meldet echte Verfügbarkeit (SearXNG down → `available: false`).
- Fortschritt ist echt: `research`-SSE-Events sind ausgeführte Schritte,
  keine Stimmungsanimation.
- Fehler bleiben sichtbar: Warnungen zur Zitatkorrektur, Lücken,
  blockierte Quellen – alle im Report und im Chat-`done`-Event.

## 6. Nutzerkontrolle

- Cache leeren: `DELETE /api/web/cache`.
- Recherche-Sessions löschen: `DELETE /api/research/{id}` (inkl. Zitate).
- Quellen + Snapshots löschen: `DELETE /api/sources/{id}`.
- Recherche gezielt aus: Chat-Steuerung `research: off` (und der
  Kontext-Preview recherchiert grundsätzlich nie live).
- Speicherzwang: `enforce_limits` + TTL im Repo-Layer halten Snapshots und
  Cache klein (docs/SOURCE_MANAGEMENT.md).
