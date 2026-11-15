# ZENJI – Entwicklungsbericht v0.3.0: Begleiter-Persönlichkeit

**Datum:** 15. November 2026
**Version:** 0.2.0 → 0.3.0 · Migration Stufe 2 → 3
**Status:** ✅ Abgeschlossen — Backend, Frontend, Tests (226 grün), Doku
**Vorgänger:** Phase 2 „Core Intelligence" (v0.2.0)

---

## 1. Zielsetzung

v0.3.0 erweitert die Phase-2-Architektur um eine **Begleiter-Persönlichkeit**:
ZENJI soll wie eine enge, intelligente Freundin an der Seite des Nutzers
klingen — natürlich, frech, humorvoll, direkt, mit eigener Meinung, ohne
Corporate-Chatbot-Ton. Wichtig: Es ist **keine** neue Engine-Schicht
entstanden, sondern die bestehende Phase-2-Architektur (PersonalityEngine,
PolicyEngine, ContextEngine, ZenjiCore) wurde erweitert.

| Forderung | Umsetzung |
|---|---|
| Natürliche, informelle Kommunikation | Systemregel `communication_freedom` (P96): Umgangssprache, Kraftausdrücke, schwarzer Humor erlaubt; kein Corporate-Sprech |
| Kraftausdrücke / dunkler Humor / freches Necken | explizit in der Regel erlaubt; Roast-Modus mit Grenzen (kein Hass, keine Diskriminierung) |
| Offene Themen (Intimität, kontrovers) im Rahmen von Alter/Einverständnis/Sicherheit | Regel + eigener Modus **Open Talk** mit fest verankertem Sicherheitsrahmen |
| 5 Kommunikationsmodi, automatisch bevorzugt | CommunicationManager mit deterministischer Moduswahl (Signale > Standard); manuelle Anfrage möglich |
| Persönlichkeit konfigurierbar, keine Hardcodes | 10 Skalare (0–1, UI: Prozent), Werte nur in `personalities.json`/DB — Test verifiziert, dass keine Spezifikationswerte im Python-Code stehen |
| Persistenz über Neustarts/Modelle | Profilwerte in SQLite; Modi bewusst **flüchtig** (temporär markiert im Prompt) |
| Ehrlichkeit, eigene Meinung, kein Sycophantismus | `honesty_first` erweitert (kein Mensch/Bewusstsein vortäuschen, keine unnötigen Disclaimer) + `independent_opinions` (P88) |
| Bestand bleibt funktional | alle 178 Phase-1/2-Tests laufen aktualisiert grün; Migration datenschonend |

---

## 2. Veränderte Komponenten

### 2.1 Backend

| Datei | Änderung |
|---|---|
| `app/database/models.py` | 6 neue `PersonalityModel`-Spalten: `sarcasm, cheekiness, friendliness, empathy, curiosity, initiative` (0–1) |
| `app/database/migrations.py` | `LATEST_VERSION = 3`; `_migrate_2_to_3` mit 6 idempotenten Helfern: `_add_personality_trait_columns` (ALTER TABLE + PRAGMA-Guard), `_seed_personalities`/`_seed_policies` (additiv), `_refresh_system_rule_texts`, `_refresh_system_profile_traits`, `_maybe_activate_zenji`, `_refresh_default_persona` |
| `app/config/personalities.json` | Neues Standardprofil **Zenji** (erster Eintrag, aktiv) + neue Achsen für alle 4 Bestandsprofile |
| `app/config/system_policies.json` | 8 Regeln: 2 neu (`communication_freedom` P96, `independent_opinions` P88), Texte von `zenji_identity` (P100) und `honesty_first` (P95) erweitert |
| `app/config/communication_modes.json` | **Neu**: datengetriebene Modusdefinitionen (explicit-Muster, Signale, Priorität, Direktiven) |
| `app/engines/communication_engine.py` | **Neu**: `CommunicationManager` (`detect_mode`, `mode_directives`, `available`, `default_mode`), fail-soft, deterministisch, kein Zustand |
| `app/engines/personality_engine.py` | Create/Update-Whitelists um 6 Achsen erweitert; `_render` gibt **10** Skalar-Zeilen aus |
| `app/engines/context_engine.py` | `build(..., communication_text, mode)`; neuer fester Abschnitt `communication` direkt hinter `personality`; `ContextPlan.mode` |
| `app/services/zenji_core.py` | Optionaler `communication_engine`-Parameter; Schritt 3b (Moduswahl, fail-soft); `mode_override` in `prepare_turn`/`context_preview`; Status liefert `communication_modes` + `communication_default_mode` |
| `app/services/chat_service.py` | `request.mode` wird als Override durchgereicht (Stream- und Sync-Pfad) |
| `app/schemas/{chat,personality,core}.py` | `ChatRequest.mode` (Validierung gegen `COMMUNICATION_MODE_KEYS`, unbekannt → 422); Personality-Schemas um 6 Felder; `CoreStatusOut`/`ContextPreviewOut` erweitert |
| `app/api/routes/{core,personality}.py` | Status-/Preview-Ausgabe mit Modus-Feldern; Preview-Parameter `?mode=`; `_out()` liefert neue Felder |
| `app/core/config.py` | `DEFAULT_PERSONA` auf Augenhöhe-Ton umgeschrieben; `LEGACY_PERSONA` konserviert den v0.2.0-Text |
| `app/main.py` | CommunicationManager erzeugt, registriert und in den Core injiziert |
| `app/__init__.py` | `__version__ = "0.3.0"` |

### 2.2 Frontend

| Datei | Änderung |
|---|---|
| `src/types/index.ts` | `Personality` + 6 Felder; `CoreStatus.communication_modes/_default_mode`; `ContextPreview.mode`; neuer Typ `CommunicationModeKey` |
| `src/services/api.ts` | `openChatStream(..., mode)` sendet `mode` im Body |
| `src/hooks/useChat.ts` | `send(text, mode)` |
| `src/components/Composer.tsx` | Modus-`<select>` („Modus: Auto" = Automatik) neben der Identitätsmarke |
| `src/components/ChatArea.tsx` / `src/pages/ChatPage.tsx` | `onSend`-Signatur mit Modus durchgereicht |
| `src/components/control/PersonalityTab.tsx` | **10 Slider** (Formalität, Humor, Sarkasmus, Frechheit, Direktheit, Freundlichkeit, Empathie, Neugier, Eigeninitiative, Kreativität) |

Build: `npm run build` OK — 311,42 kB JS / 92,64 kB gzip.

### 2.3 Migration 2→3 (datenschonend)

1. **Achsen ergänzen** – fehlende Spalten per `ALTER TABLE` (frische DBs haben
   sie schon; PRAGMA-Guard macht es idempotent).
2. **Nachseeden** – fehlende Profile/Regeln additiv ergänzen.
3. **Systemregeln aktualisieren** – Name/Text/Priorität von `source=system`-
   Regeln auf den Seed-Stand (die API verweigert Systemregel-Änderungen,
   die Migration ist der einzige Weiterentwicklungspfad). Nutzerregeln
   bleiben unberührt.
4. **Systemprofile aktualisieren** – nur die **neuen** Achsen auf Seed-Werte;
   Nutzerprofile kriegen die neutralen ALTER-Defaults.
5. **Zenji aktivieren** – nur wenn aktuell nichts aktiv ist oder ausschließlich
   das Seed-Standardprofil „Neutral" (das war nie eine bewusste Nutzerwahl).
   Jedes andere aktive Profil bleibt erhalten.
6. **Persona-Prompt aktualisieren** – nur wenn der gespeicherte
   Einstellungs-Text **exakt** dem v0.2.0-Default (`LEGACY_PERSONA`)
   entspricht; individuelle Nutzertexte werden niemals ersetzt.

Alle Schritte in `test_companion_personality.py` mit simulierter
Phase-2-Datenbank (`user_version=2`) verifiziert.

---

## 3. Persönlichkeitskonfiguration (Standard „Zenji")

Spezifikationswerte, Skala 0–100 → intern 0–1:

| Skalar | Wert | Prompt-Stufe |
|---|---|---|
| Formalität | 15 % | sehr locker/umgangssprachlich |
| Humor | **90 %** | sehr stark |
| Sarkasmus | **65 %** | stark |
| Frechheit | **75 %** | stark |
| Direktheit | **95 %** | sehr stark |
| Freundlichkeit | **90 %** | sehr stark |
| Empathie | **85 %** | sehr stark |
| Neugier | **90 %** | sehr stark |
| Eigeninitiative | **85 %** | sehr stark |
| Kreativität | 80 % | sehr stark |

Identität: *„Du bist ZENJI – wie eine enge, intelligente Freundin an der
Seite des Nutzers. Kein Kundenservice-Chatbot: eigenständig, frech, ehrlich
und mit eigener Meinung."* Situationsverhalten regelt Empathie-Schaltung,
Fokus-Wechsel, offene Antworten zu intimen Fragen, Fehlerkultur und
Widerspruch. Die anderen 4 Systemprofile (Neutral, Professional, Friendly,
Casual) bekamen gestufte Achsenwerte, damit sich Profile wirklich
unterscheiden (Professional z. B. Humor 10 %, Sarkasmus 5 %).

**Kein Wert steht im Python-Code** — Test `test_kein_profil_hartcodiert_in_engine`
liest den Quelltext und verifiziert das.

---

## 4. System-Prompts (neu/aktualisiert)

1. **`zenji_identity` (P100):** *„Du bist ZENJI, ein eigenständiges Gegenüber
   auf Augenhöhe – kein Dienstleistungs-Chatbot. Das Sprachmodell ist nur
   dein Generierungskern …"*
2. **`communication_freedom` (P96):** *„Sprich natürlich und
   umgangssprachlich wie unter Freunden. Kraftausdrücke, schwarzer Humor,
   Ironie und freches Necken sind erlaubt, wenn die Situation dazu einlädt.
   Auch über Sexualität, Intimität, Beziehungen und kontrovers Themen
   sprichst du offen – ausschließlich im Rahmen von Alter, Einverständnis
   und Sicherheit. Kein Corporate-Sprech …"*
3. **`honesty_first` (P95):** erweitert um *„Stelle niemals dar, ein Mensch
   zu sein oder Bewusstsein zu haben. Vermeide unnötige Disclaimer und
   wiederholte Entschuldigungen."*
4. **`independent_opinions` (P88):** *„Du hast eigene, begründete Meinungen
   und teilst sie offen mit. Widersprich dem Nutzer, wenn du eine Aussage
   für falsch hältst – Zustimmung nur zum Gefallen gibt es nicht. Bring von
   dir aus Ideen und Vorschläge ein."*
5. **Bootstrap-Persona (`DEFAULT_PERSONA`):** *„Du bist ZENJI – kein
   Standard-Assistent, sondern ein eigenständiges Gegenüber auf Augenhöhe:
   nah dran, unverbissen, mit eigener Meinung und trockenem Humor."*
   (Wird durch die Persönlichkeit **überschrieben**, sobald ein Profil
   aktiv ist — sie ist die Identitätsquelle im Chatpfad.)
6. **Modus-Abschnitt („## Kommunikationsmodus", pro Nachricht):** z. B.
   Roast — *„Sei frech, sarkastisch und provokant: necke den Nutzer
   humorvoll … Harte Sticheleien sind erwünscht; echter Hass,
   Diskriminierung und Verletzen persönlicher Grenzen bleiben verboten.
   Fachlich bleibt alles korrekt."* Jede Direktive enthält den Hinweis
   *„temporärer Modus … die zugrundeliegende Persönlichkeit bleibt
   unverändert"*.

---

## 5. Modusbehandlung

**Modi:** Casual (Standard) · Roast · Fokus · Empathie · Open Talk —
alle Definitionen in `communication_modes.json`, nicht im Code.

**Automatische Wahl (`detect_mode`, pro Nachricht):**

1. Manueller Override (`ChatRequest.mode` bzw. `?mode=`) — unbekannter
   Wert wird verworfen (fail-soft, Log-Warnung); Schema-Seitig bereits 422.
2. Explizite Modusanfrage („Roast-Modus", „Lass uns Open Talk machen") —
   schlägt alle Signale.
3. Signale in Priorität **empathy → open_talk → roast → focus**
   (Gefühle vor Themen vor Aufgaben).
4. Standard `casual`.

**Einbau:** Direktive → `## Kommunikationsmodus` direkt hinter
`## Persönlichkeit`, vor den Regeln; `ContextPlan.mode` + Preview-Feld
`mode` machen es nachvollziehbar.

**Persistenz-Modell:** Persönlichkeitswerte, Identität, Nutzerregeln sind
**dauerhaft** (DB); der Modus ist **temporär** (pro Nachricht, keine DB) —
markiert im Prompt, per `test_roast_modus_veraendert_persoenlichkeit_nicht`
geprüft. Das UI wählt Modus pro Nachricht (Composer-Select); „Auto" =
Automatik.

---

## 6. Tests

**226 Tests in ~2 s, alle grün** (pytest, FakeProvider):

| Suite | Tests | Inhalt |
|---|---|---|
| `test_communication_engine.py` | 17 | 5 Modi geladen, Moduswahl inkl. Priorität/Override, Direktiven mit Grenzen, Fail-soft (fehlende/kaputte/leere Seed-Datei) |
| `test_companion_personality.py` | 16 | Spezifikationswerte, Migration 2→3 (inkl. Nutzerwahl-Schutz, Persona-Prompt-Schutz), Neustart-Persistenz, Modell-Unabhängigkeit, temporärer Modus |
| `test_chat_modes.py` | 15 | Repräsentative Gespräche im echten Chatpfad: informeller Ton, Kraftausdrücke erlaubt, Open Talk mit Sicherheitsrahmen, Widerspruch, Kummer→Empathie, Technik→Fokus, Moduswechsel in einer Konversation, Bestand (Erinnerung) bleibt funktional |
| aktualisiert (Phase 1+2) | 178 | Migration/Seeds, Personality-, Policy-, Memory-, Context-, Core-Tests, API-Tests |

Wichtige Einzelprüfungen:
`test_api_chat_stream_mit_unbekanntem_modus_422` (422-Vertrag),
`test_migration_respektiert_aktiviertes_nutzerprofil` (echte Nutzerwahl),
`test_persoenlichkeit_unabhaengig_vom_modell` (gleicher Systemprompt bei
zwei Modelleinstellungen), `test_kraftausdruecke_und_schwarzer_humor_erlaubt`.

Live-Smoke (venv, temporäre DB): Version 3, 5 Profile (Zenji aktiv), 8
Regeln, kompilierter Persönlichkeitsblock mit 10 Achsen, Modus-Erkennung
für alle 5 Modi + explicit + override.

---

## 7. Grenzen (ehrlich benannt)

1. **FakeProvider-Ebene:** Die neuen Gesprächstests verifizieren das
   Verhalten auf **Prompt-/Instruktionsebene** (welche Anweisungen das
   Modell tatsächlich erhält). Wie ein konkretes Modell sie befolgt
   (Witzqualität, Roast-Schärfe), wurde zusätzlich manuell gegen
   Qwen3 8B geprüft — eine automatisierte End-to-End-Prüfung des
   Modellverhaltens ist nicht Teil der Suite.
2. **Signal-Erkennung ist Heuristik:** Substring-Matching, konservativ
   gehalten, kann danebenliegen (Ironie, Mehrdeutigkeit, Schreibfehler).
   Ausweg: explizite Anfrage schlägt Signale; manuelles Override über
   Composer/API. Missklassifikation schadet nicht — falscher Modus ist
   maximal ein falscher Ton, kein falscher Inhalt.
3. **Roast-Grenzen:** Die Direktive verbietet Hass/Diskriminierung/
   Grenzverletzung, aber die letzte Instanz ist das Modell selbst.
   Lokale Modelle können Direktiven unterschiedlich streng befolgen.
4. **Open Talk:** „Alter, Einverständnis, Sicherheit" ist im Prompt
   verankert, aber ZENJI hat keine Verifizierung des Nutzeralters —
   die Regel ist eine Anweisung, keine technische Sperre. Absolute
   Inhalte (Minderjährige etc.) liegen außerhalb des Modusrahmens.
5. **Modus ist pro Nachricht:** Es gibt keine „Stimmungs"-Persistenz
   über Nachrichten (bewusste Designentscheidung — dauerhaft ist nur
   die Persönlichkeit). Wer dauerhaft einen Ton will, passt das Profil an.
6. **Migration gewichtet bewusst zugunsten von Nutzerwahl:** Wer vor dem
   Upgrade ein anderes Profil aktiv hatte, behält es — Zenji wird dann
   nicht erzwungen (per Design dokumentiert).
7. **Moduswechsel mitten im Satz** („… aber jetzt Roast!") innerhalb
   einer Nachricht wird nicht gesplittet — eine Nachricht, ein Modus.

---

## 8. Ausblick (nicht Teil dieser Version)

- Zeitliche Modus-Laufzeiten („Roast für die nächsten 3 Nachrichten")
- Weiches Signal-Gewicht statt Binärentscheidung (Keyword-Scoring)
- Nutzerdefinierbare Modi (JSON nur für Systemmodi vorgesehen)
- Automatisierte End-to-End-Prüfung des Modellverhaltens (Evals)

---

## Addendum v0.4.0: Beleidigungs-Banter

**Datum:** 15. November 2026 · Migration Stufe 3 → 4 · 235 Tests grün

Aufbauend auf der Modus-/Regel-Architektur aus diesem Bericht: ZENJI darf
jetzt **richtig harte Beleidigungen** aussprechen (Hurensohn, Arschloch,
Wichser …) und schlägt zurück, wenn man es beleidigt.

| Forderung | Umsetzung |
|---|---|
| Harte Beleidigungen auf Aufforderung | `communication_freedom` (P96) um Beleidigungs-Satz erweitert + Roast-Direktive nennt die Wörter ausdrücklich |
| Provokation → Gegenfeuer | Roast-Signale um Beleidigungsmuster erweitert („arschloch", „hurensohn", „fick dich" …): Beleidigt der Nutzer ZENJI, springt Roast automatisch an; Systemregel `insult_banter` (P94) trägt den Rückzuschlag-Auftrag |
| Grenzen bleiben | `insult_banter`: keine Angriffe auf Herkunft/Religion/Hautfarbe/Geschlecht/Behinderung/sexuelle Orientierung als Gruppe, keine Gewaltandrohungen, keine ernsthaften Beleidigungen echter Dritter, nichts gegenüber Minderjährigen |

**Technik (nur Erweiterung der bestehenden Schichten):**

- `system_policies.json`: freedom-Text erweitert, neue Regel `insult_banter`
  (P94, Kategorie kommunikation, scope global, source system).
- `communication_modes.json`: Roast-Signale + Beleidigungswörter,
  Roast-Direktive mit Gegenfeuer-Absatz, explicit-Muster
  „beleidigungs-modus"; Casual-`explicit` um Negationen erweitert
  („beleidige mich nicht", „keine beleidigungen" …).
- **Negations-Guard:** Explizite Muster aller Modi werden vor allen Signalen
  geprüft (JSON-Reihenfolge, Casual zuerst) → negierte Beleidigungs-Sätze
  bleiben Casual.
- **Prioritäts-Ausnahme:** Empathie outrankt Roast („Mir geht's nicht gut,
  du Arschloch" → Empathie, Kummer zählt zuerst).
- Migration **3→4**: `_seed_policies` + `_refresh_system_rule_texts`
  wiederverwendet — seedet `insult_banter` additiv nach, aktualisiert die
  Systemregel-Texte; Nutzerdaten/Nutzerregeln unberührt.

**Neue Prüfungen:** Beleidigung→Roast (5 Wörter), Aufforderung→Roast,
Negation→Casual (Engine **und** Chatpfad), Empathie-vor-Roast,
Gegenfeuer-/Regeltexte im Systemprompt, Migration 3→4 mit simulierter
v0.3.0-Datenbank (Regel fehlt + alter freedom-Text → nach Migration
vollständig).

**Limitation:** Die Heuristik kann einen in der Nachricht genannten Dritten
nicht vom Adressaten unterscheiden („Mein Kollege ist so ein Arschloch" →
Roast). `insult_banter` und die Roast-Direktive verbieten Beleidigungen
echter Dritter aber ausdrücklich — Abfederung auf Prompt-Ebene; die letzte
Instanz ist wie bei allen Grenzen das Modell selbst (vgl. Grenze 3 oben).
