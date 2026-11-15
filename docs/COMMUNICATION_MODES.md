# Kommunikationsmodi (v0.3.0)

ZENJI passt seinen Ton der Situation an. Fünf Modi steuern **wie** geantwortet
wird – nicht **wer** antwortet: Die Persönlichkeit (Profil) bleibt bei jedem
Modus unverändert; ein Modus ist eine temporäre Stimmung, keine
Persönlichkeitsänderung.

| Modus | Ton |
|---|---|
| **Casual** (Standard) | locker, freundlich, humorvoll – wie unter Freunden |
| **Roast** | frech, sarkastisch, provokant; Grenzen und Fachlichkeit bleiben gewahrt |
| **Fokus** | konzentriert, präzise, lösungsorientiert, wenig Abschweifung |
| **Empathie** | ruhig, warm, verständnisvoll; Humor nur behutsam |
| **Open Talk** | offen zu persönlichen, intimen und kontroversen Themen – immer im Rahmen von Alter, Einverständnis und Sicherheit |

## 1. Wo die Modi leben

`backend/app/config/communication_modes.json` – datengetrieben, **kein
Python-Hardcoding**. Pro Modus:

- `key` / `label` – stabile ID und Anzeigename
- `explicit` – Muster für eine **explizite Modusanfrage** („Roast-Modus")
- `signals` – Muster für **automatische Erkennung** (Inhalt-Signale)
- `directive` – Stilvorgabe, die in den Prompt übersetzt wird

Global: `default` (Standardmodus `casual`) und `priority` (Signal-Reihenfolge:
`empathy` → `open_talk` → `roast` → `focus`).

## 2. Moduswahl (`CommunicationManager.detect_mode`)

Reihenfolge, pro Nachricht neu entschieden:

1. **Manueller Override** – `ChatRequest.mode` bzw. Preview-Parameter. Ein
   unbekannter Wert wird verworfen und die Automatik genutzt (fail-soft,
   mit Warnung im Log).
2. **Explizite Modusanfrage** – Nutzer schreibt z. B. „Wechsle in den
   Roast-Modus" oder „Lass uns Open Talk machen". Schlägt alle Signale.
3. **Signal-Priorität** – Gefühle vor Themen vor Aufgaben:
   - Empathie-Signale („mir geht's nicht gut", „Job verloren", „gestorben" …)
   - Open-Talk-Signale („Sex", „Beziehung", „kontrovers", „ungefiltert" …)
   - Roast-Signale („roaste mich", „sei frech", „neck mich" …)
   - Fokus-Signale („debugge", „Funktion", „SQL", „Anleitung" …)
4. **Standard** – nichts passt → `casual`.

Die Erkennung ist deterministisch (Substring-Matching, kleingeschrieben),
modellunabhängig und ohne LLM-Aufruf. Fehlt die JSON-Datei, läuft der Chat
im Standardmodus ohne Modusabschnitt weiter (fail-soft).

## 3. Einbau in den Prompt

Der CommunicationManager liefert pro Nachricht einen Abschnitt:

```
## Kommunikationsmodus
Aktuell: Roast (temporärer Modus für diese Unterhaltung – die zugrundeliegende
Persönlichkeit bleibt unverändert).
Sei frech, sarkastisch und provokant: necke den Nutzer humorvoll, …
```

Die ContextEngine fügt ihn **direkt hinter der Persönlichkeit** ein (fester
Abschnitt, vor den Regeln) und protokolliert den Modus im `ContextPlan`
(`plan.mode`) – sichtbar in der Kontext-Preview.

## 4. Manuelle Modusanfrage

- **UI**: Modus-Auswahl im Composer („Modus: Auto" = Automatik).
- **API**: `POST /api/chat` / `/api/chat/stream` mit `"mode": "roast"`.
  Zulässige Werte: `casual | roast | focus | empathy | open_talk`;
  jeder andere Wert → HTTP 422.
- **Kontext-Preview**: `GET /api/core/context-preview?mode=roast` zeigt den
  Entwurf für den erzwungenen Modus; die Antwort enthält `mode`.
- **Status**: `GET /api/core/status` listet `communication_modes`
  (`[{key, label}]`) und `communication_default_mode`.

## 5. Grenzen (bewusst so gebaut)

- Modi sind **flüchtig**: Es gibt keine „Stimmungs"-Persistenz. Was dauerhaft
  ist, steht im Profil; was temporär ist, steht im Prompt-Abschnitt.
- Modusdirektiven **verbieten** nie weniger als die Systemregeln
  (`communication_freedom`): Necken ja, Hass/Diskriminierung/Grenzverletzung
  nein; Open Talk ja, außerhalb von Alter/Einverständnis/Sicherheit nein.
- Die Signal-Erkennung ist bewusst konservativ gehalten (keine
  Übertreibung), kann aber wie jede Heuristik danebenliegen. Der manuelle
  Override ist der Ausweg – und explizite Anfragen schlagen Signale.
