# Personality Engine (Phase 2 + v0.3.0 Begleiter-Persönlichkeit)

Die Personality Engine verwaltet die **identitätsbildenden Profile** von ZENJI.
Sie ist die Antwort auf die Kernforderung: ZENJI soll nicht das Sprachmodell
sein, sondern das Sprachmodell ist nur sein Generierungskern. Die
Persönlichkeit liegt in Daten (DB + Seed-Dateien), nicht im Python-Code.

Seit v0.3.0 ist das Standardprofil **Zenji** eine Begleiter-Persönlichkeit:
freundlich, frech, humorvoll, direkt, eigenständig (siehe Abschnitt 2).

## 1. Datenmodell

Tabelle `personalities` (siehe STORAGE.md):

| Feld | Typ | Bedeutung |
|---|---|---|
| `id` | str | UUID |
| `name` | str | Anzeigename (eindeutig) |
| `identity` | str | Freitext-Identität („Du bist ZENJI als …") |
| `base_personality` | str | `neutral` / `professional` / `friendly` / `casual` / `custom` |
| `communication_style` | str | Freitext-Stilbeschreibung |
| `formality`, `humor`, `directness`, `creativity` | float 0–1 | Skalare Eigenschaften (Phase 2) |
| `sarcasm`, `cheekiness`, `friendliness`, `empathy`, `curiosity`, `initiative` | float 0–1 | Skalare Eigenschaften (v0.3.0, Migration 2→3) |
| `response_length` | str | `short` / `balanced` / `detailed` |
| `language` | str | `auto` (Sprache des Nutzers), `de`, `en`, … |
| `situational_behavior` | JSON | `{ "Situation": "Verhalten" }` |
| `is_system` | bool | Systemprofil (Seed) – löschgeschützt |
| `is_active` | bool | Genau **ein** Profil ist aktiv |

Alle Skalare werden als **Prozent-Slider (0–100 %)** im Control Center
bedient und intern als 0–1 gespeichert. Es gibt **keine hartcodierten
Persönlichkeitswerte im Python-Code** – Werte leben ausschließlich in
`personalities.json` bzw. der Datenbank.

## 2. Seed-Profile

`backend/app/config/personalities.json` wird beim Start/Migrationslauf
idempotent eingespielt:

| Profil | Charakter | Besetzung (Humor/Sarkasmus/Frechheit/Direktheit/Freundlichkeit/Empathie/Neugier/Initiative) |
|---|---|---|
| **Zenji** | Begleiterin: nah, frech, ehrlich, eigenständig – **Standard aktiv** (v0.3.0) | 90 / 65 / 75 / 95 / 90 / 85 / 90 / 85 |
| **Neutral** | Sachlich, ausgewogen (ehemaliger Standard) | 20 / 10 / 10 / 60 / 50 / 40 / 40 / 30 |
| **Professional** | Sehr formell, strukturiert, ausführlich | 10 / 5 / 5 / 70 / 40 / 35 / 50 / 45 |
| **Friendly** | Warm, zugewandt, humorvoll-moderat | 55 / 30 / 25 / 45 / 90 / 80 / 70 / 60 |
| **Casual** | Locker, direkt, knapp | 70 / 55 / 60 / 75 / 80 / 60 / 75 / 70 |

Aktivierung: Bei frischer Datenbank wird der **erste Seed-Eintrag** (Zenji)
aktiv. Bei Upgrade von Phase 2 (v2→v3) wird Zenji aktiviert, solange nur das
ehemalige Seed-Standardprofil „Neutral" aktiv ist; ein bewusst gewähltes
Nutzerprofil bleibt unangetastet („echte Nutzerwahl wird respektiert").

Systemprofile (`is_system=true`) können **bearbeitet**, aber nicht gelöscht
werden (`PERSONALITY_PROTECTED`, 409). Nutzerprofile sind frei erstell- und
löschbar; ein aktives Profil ist löschgeschützt (erst anderes aktivieren).

## 3. Kompilierung (`compile_context`)

Die Engine übersetzt ein Profil in einen deterministischen
Persönlichkeits-Kontextblock, der von der ContextEngine in den
Systemprompt eingebaut wird:

```
## Persönlichkeit
Name: Zenji
Identität: <identity>
Grundhaltung: friendly
Kommunikationsstil: <communication_style>
Formalität: sehr locker/umgangssprachlich   ← _level() bildet 0–1 auf Textstufen ab
Humor: sehr stark
Sarkasmus: stark
Frechheit: stark
Direktheit: sehr stark
Freundlichkeit: sehr stark
Empathie: sehr stark
Neugier: sehr stark
Eigeninitiative: sehr stark
Kreativität: sehr stark
Antworte ausführlich genug, …   ← response_length
Antworte in der Sprache, in der der Nutzer schreibt.  ← language=auto
Verhalten in besonderen Situationen:
- Situation 'Ernsthafter Moment oder Kummer': …   ← situational_behavior
```

Ohne aktives Profil entsteht ein bewusst neutraler Fallback-Block
(„Kein Profil aktiv") – der Chat läuft trotzdem.

## 4. Aktivierung

`activate(profile_id)` setzt in **einer** Transaktion alle anderen Profile
auf `is_active=false` und das Zielprofil auf `true`. Der Chatpfad liest über
`require_active()` genau dieses eine Profil. Aktivieren geht über
`POST /api/personality/{id}/activate` oder `PATCH … {"is_active": true}`.

## 5. API

| Endpoint | Verhalten |
|---|---|
| `GET /api/personality` | Alle Profile, aktives zuerst |
| `POST /api/personality` | Nutzerprofil anlegen (201) |
| `PATCH /api/personality/{id}` | Teilweise Änderung (alle 10 Skalare erlaubt) |
| `POST /api/personality/{id}/activate` | Aktivieren, genaues Einzelaktiv |
| `GET /api/personality/{id}/preview` | Kompilierter Kontextblock (Vorschau) |
| `DELETE /api/personality/{id}` | 204; 409 bei System-/Aktiv-Schutz |

## 6. Zusammenspiel mit anderen Engines

```
PersonalityEngine.compile_context(profile)
        │  (ein Textblock)
        ▼
ZenjiCore.prepare_turn ──► CommunicationManager.detect_mode ──► mode_directives
        │                              │   (Abschnitt „## Kommunikationsmodus")
        ▼                              ▼
ContextEngine.build(personality_text=…, communication_text=…, mode=…)
                                   │
                                   ▼
                     Zusammengeführter Systemprompt:
       Identität → Persönlichkeit → Kommunikationsmodus → Regeln → …
```

- **ZenjiCore** ruft `require_active()` + `compile_context()` in Schritt 3
  und danach den CommunicationManager (Schritt 3b) auf.
- **ContextEngine** fügt den Persönlichkeitsblock als festen Abschnitt ein
  (nie gekürzt); der Modus-Abschnitt folgt direkt danach.
- **PolicyEngine** bleibt unabhängig: Regeln gelten für alle Profile;
  die Persönlichkeit färbt nur den Stil.

### Trennung permanent vs. temporär

- **Permanent** (Datenbank, überlebt Neustarts und Modellwechsel): Profilwerte
  (`humor`, `sarcasm`, …), Identität, Situationsverhalten, Nutzerregeln.
- **Temporär** (pro Nachricht, flüchtig): der Kommunikationsmodus. Der
  Modus-Abschnitt markiert sich im Prompt ausdrücklich als „temporärer Modus
  für diese Unterhaltung – die zugrundeliegende Persönlichkeit bleibt
  unverändert". Ein Roast-Tag ändert niemals die gespeicherten Profilwerte
  (getestet in `test_companion_personality.py`).
