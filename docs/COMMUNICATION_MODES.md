# Kommunikationsmodi (v0.3.0, erweitert in v0.4.0)

ZENJI passt seinen Ton der Situation an. Fünf Modi steuern **wie** geantwortet
wird – nicht **wer** antwortet: Die Persönlichkeit (Profil) bleibt bei jedem
Modus unverändert; ein Modus ist eine temporäre Stimmung, keine
Persönlichkeitsänderung.

| Modus | Ton |
|---|---|
| **Casual** (Standard) | locker, freundlich, humorvoll – wie unter Freunden |
| **Roast** | frech, sarkastisch, hemmungslos; harte Beleidigungen ausdrücklich Teil des Spiels, Gegenfeuer bei Provokation; Hass/Diskriminierung/Gewalt bleiben verboten, Fachlichkeit gewahrt |
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
   Roast-Modus", „Beleidigungs-Modus an" oder „Lass uns Open Talk machen".
   Schlägt alle Signale.
3. **Signal-Priorität** – Gefühle vor Themen vor Aufgaben:
   - Empathie-Signale („mir geht's nicht gut", „Job verloren", „gestorben" …)
   - Open-Talk-Signale („Sex", „Beziehung", „kontrovers", „ungefiltert" …)
   - Roast-Signale („roaste mich", „sei frech", „neck mich", „beleidige mich",
     „hurensohn", „arschloch", „wichser", „fick dich", „verpiss dich" … –
     v0.4.0: Beleidigungen gegen ZENJI und Beleidigungs-Aufforderungen)
   - Fokus-Signale („debugge", „Funktion", „SQL", „Anleitung" …)
4. **Standard** – nichts passt → `casual`.

Die Erkennung ist deterministisch (Substring-Matching, kleingeschrieben),
modellunabhängig und ohne LLM-Aufruf. Fehlt die JSON-Datei, läuft der Chat
im Standardmodus ohne Modusabschnitt weiter (fail-soft).

### 2.1 Beleidigungs-Banter (v0.4.0)

Zwei Wege führen in den Roast-Modus – und damit zur Erlaubnis für harte
Beleidigungen (Hurensohn, Arschloch, Wichser, Missgeburt …):

- **Provokation → Gegenfeuer:** Beleidigt der Nutzer ZENJI („Du Arschloch!"),
  springt der Roast-Modus automatisch an; die Direktive und die Systemregel
  `insult_banter` (P94) tragen den Auftrag „mit gleicher Härte zurückschlagen".
- **Aufforderung:** „Beleidige mich mal richtig" oder explizit
  „Beleidigungs-Modus" aktivieren Roast ebenso.

**Negations-Schutz:** Die Casual-Modi-`explicit`-Liste enthält negierte
Formen („beleidige mich nicht", „keine beleidigungen", „ohne beleidigungen"
…). Explizite Muster aller Modi werden **vor** allen Signalen geprüft
(JSON-Reihenfolge, Casual zuerst) – „Erklär mir async, aber beleidige mich
nicht" bleibt also Casual, obwohl „beleidig …" auch ein Roast-Signal wäre.

**Prioritäts-Ausnahme:** Empathie-Signale outranken Beleidigungssignale
(Priorität `empathy` → `roast`). „Mir geht's nicht gut, du Arschloch" →
Empathie statt Roast: Der Kummer zählt zuerst.

**Heuristik-Limitation:** Die Substring-Erkennung kann einen im Satz genannten
Dritten nicht vom Adressaten unterscheiden („Mein Kollege ist so ein Arschloch"
löst Roast aus). Die Roast-Direktive und `insult_banter` verbieten aber
ausdrücklich ernsthafte Beleidigungen echter Dritter – auf Prompt-Ebene
abgefedert, nicht auf Erkennungsebene.

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
