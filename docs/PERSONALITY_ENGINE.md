# Personality Engine (Phase 2)

Die Personality Engine verwaltet die **identitätsbildenden Profile** von ZENJI.
Sie ist die Antwort auf die Kernforderung: ZENJI soll nicht das Sprachmodell
sein, sondern das Sprachmodell ist nur sein Generierungskern. Die
Persönlichkeit liegt in Daten (DB + Seed-Dateien), nicht im Python-Code.

## 1. Datenmodell

Tabelle `personalities` (siehe STORAGE.md):

| Feld | Typ | Bedeutung |
|---|---|---|
| `id` | str | UUID |
| `name` | str | Anzeigename (eindeutig) |
| `identity` | str | Freitext-Identität („Du bist ZENJI als …") |
| `base_personality` | str | `neutral` / `professional` / `friendly` / `casual` / `custom` |
| `communication_style` | str | Freitext-Stilbeschreibung |
| `formality`, `humor`, `directness`, `creativity` | float 0–1 | Skalare Eigenschaften |
| `response_length` | str | `short` / `balanced` / `detailed` |
| `language` | str | `auto` (Sprache des Nutzers), `de`, `en`, … |
| `situational_behavior` | JSON | `{ "Situation": "Verhalten" }` |
| `is_system` | bool | Systemprofil (Seed) – löschgeschützt |
| `is_active` | bool | Genau **ein** Profil ist aktiv |

## 2. Seed-Profile

`backend/app/config/personalities.json` wird beim Start/Migrationslauf
idempotent eingespielt:

| Profil | Charakter |
|---|---|
| **Neutral** | Sachlich, ausgewogen – **Standard aktiv** |
| **Professional** | Sehr formell, strukturiert, ausführlich |
| **Friendly** | Warm, zugewandt, humorvoll-moderat |
| **Casual** | locker, direkt, knapp |

Systemprofile (`is_system=true`) können **bearbeitet**, aber nicht gelöscht
werden (`PERSONALITY_PROTECTED`, 409). Nutzerprofile sind frei erstell- und
löschbar; ein aktives Profil ist löschgeschützt (erst anderes aktivieren).

## 3. Kompilierung (`compile_context`)

Die Engine übersetzt ein Profil in einen deterministischen
Persönlichkeits-Kontextblock, der von der ContextEngine in den
Systemprompt eingebaut wird:

```
## Persönlichkeit
Name: Neutral
Identität: <identity>
Stil: <communication_style>
Formalität: ausgeglichen          ← _level() bildet 0–1 auf Textstufen ab
Humor: dezent
Direktheit: auf den Punkt
Kreativität: ausgewogen
Antworte ausführlich genug, um substantiell zu sein, …   ← response_length
Sprache: Antworte in der Sprache, in der der Nutzer schreibt.  ← language=auto
Verhalten in besonderen Situationen:
- Situation 'Fehler oder Unsicherheit': …   ← situational_behavior
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
| `PATCH /api/personality/{id}` | Teilweise Änderung (Umlaute→JSON via `_json_text`) |
| `POST /api/personality/{id}/activate` | Aktivieren, genaues Einzelaktiv |
| `GET /api/personality/{id}/preview` | Kompilierter Kontextblock (Vorschau) |
| `DELETE /api/personality/{id}` | 204; 409 bei System-/Aktiv-Schutz |

## 6. Zusammenspiel mit anderen Engines

```
PersonalityEngine.compile_context(profile)
        │  (ein Textblock)
        ▼
ZenjiCore.prepare_turn ──► ContextEngine.build(personality_text=…)
                                   │  Abschnitt „## Persönlichkeit"
                                   ▼
                          Zusammengeführter Systemprompt
```

- **ZenjiCore** ruft `require_active()` + `compile_context()` in Schritt 3b.
- **ContextEngine** fügt den Block als festen Abschnitt ein (nie gekürzt).
- **PolicyEngine** bleibt unabhängig: Regeln gelten für alle Profile;
  die Persönlichkeit färbt nur den Stil.
