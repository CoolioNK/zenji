# Context Engine (Phase 2)

Die Context Engine ist die **letzte Instanz vor dem Modell**: Sie
kompiliert Identität, Persönlichkeit, Regeln, Erinnerungen, Verlauf und
die aktuelle Anfrage zu exakt der Nachrichtenliste, die ZENJI an das
Sprachmodell sendet – deterministisch, budget-begrenzt und vollständig
nachvollziehbar.

## 1. Grundaufbau der Nachrichtenliste

**Eine zusammengeführte Systemnachricht** mit beschrifteten Abschnitten,
danach der chronologische Verlauf, dann die aktuelle Anfrage:

```
[1] system:  ## Identität            ← SettingsService (persona.system_prompt)
             ## Persönlichkeit       ← PersonalityEngine.compile_context()
             ## Regeln               ← PolicyEngine.compile().context_text
             ## Erinnerungen         ← MemoryEngine-Auswahl in Datenblöcken
             ## Zusammenfassung älterer Nachrichten   ← nur bei Kürzung
             ## Sicherheitshinweis   ← nur bei Injection-Flags
[2..n] user/assistant:            ← Verlauf (gekürzt, wenn nötig)
[n+1] user:                       ← aktuelle Anfrage
```

Rollenfolge bleibt konform: `["system", "user", …]`. Ein Systemprompt
(statt vieler wechselnder Systemnachrichten) ist für lokale Modelle
robuster und token-effizienter.

## 2. Token-Budget

Heuristik ohne Tokenizer-Abhängigkeit (modellunabhängig!):

- `estimate_tokens(text) = ceil(len(text) / 3.6)` – konservativ für Deutsch.
- `budget = num_ctx − num_predict − 256` (Marge), Minimum **512**.
- Überplanung wird im `ContextPlan` transparent (used/budget, Ratio).

## 3. Kürzungsreihenfolge bei Engpass

1. **Erinnerungen:** Score-aufsteigend verwerfen (relevanteste bleiben);
   Dubletten werden vorher ausgefiltert (normalisierter Inhalt).
2. **Verlauf:** jüngste Nachrichten behalten (`HISTORY_KEEP_MIN = 4`
   bleiben möglichst immer), ältere fallen in eine **extraktive
   Zusammenfassung** – Anfang jeder verdrängten Nachricht (120 Zeichen,
   max. 12 Einträge, bewusst **keine** Fake-LLM-Zusammenfassung).
3. **Zusammenfassung** selbst wird stufenweise verkleinert (weniger
   Einträge), falls das Budget weiter schrumpft.

Feste Abschnitte (Identität, Persönlichkeit, Regeln) werden **nie**
gekürzt – sie definieren ZENJI.

## 4. Datenblöcke (struktureller Injection-Schutz)

Erinnerungsinhalte sind **Daten**, nie Anweisungen:

```
- Erinnerung (Typ: preference · Kategorie: identität · Quelle: chat ·
  Relevanz-Score: 0.85):
[INHALT_BEGINN]
Der Nutzer heißt Max.
[INHALT_ENDE]
(Hinweis: Zu dieser Erinnerung existiert eine widersprüchliche weitere.
 Nachfragen statt raten.)    ← nur bei conflict=True
```

Zusammen mit der Systemregel `injection_defense` ist damit zweifach
sichergestellt, dass gespeicherte Inhalte den Systemprompt nicht
umkonfigurieren können.

## 5. Nachvollziehbarkeit (`ContextPlan`)

Jeder `build`-Aufruf protokolliert:

```python
ContextPlan(
  sections=[ContextSection(key, title, tokens_est, detail)],
  budget_tokens, used_tokens,
  history_kept, history_dropped,      # Verlaufskürzung
  memories_kept, memories_dropped,    # Erinnerungsauswahl
  conflicts,                          # widersprüchliche Erinnerungen
  flags,                              # Injection-Muster der Anfrage
  system_text,                        # der exakte Systemprompt
  used_memory_ids,                    # für mark_used() in Schritt 12
)
```

Die API stellt dies als `GET /api/core/context-preview` bereit
(inkl. gekürzter Nachrichtenvorschau) – der Nutzer kann im Control
Center **exakt sehen**, was das Modell bekommt. Keine Blackbox.

## 6. API

| Endpoint | Verhalten |
|---|---|
| `GET /api/core/context-preview` | Entwurf ohne LLM-Aufruf; `message` (Pflicht-optional, Default „Was kannst du?"), `conversation_id` (optional, dann mit Verlauf) |

## 7. Zusammenspiel mit allen Engines

```
SettingsService.effective() ──── system_identity ─┐
PersonalityEngine.compile_context() ──────────────┤
PolicyEngine.compile().context_text ──────────────┤   build()
PolicyEngine.check_incoming().flags ──────────────┤ ───────► (messages[],
MemoryEngine.collect_relevant() ── MemoryCandidate ┘            ContextPlan)
ConversationService.history() ──── ChatMessage[]
ChatService ────────────────────── current_message
```

- **ZenjiCore** sammelt alle Eingaben (Schritte 2–7) und ruft `build()` auf.
- Der Plan-Rückkanal: `used_memory_ids` → `finalize_turn()` →
  `MemoryEngine.mark_used()`.
- **Phase 3-Erweiterungen** (Web-/Tool-Ergebnisse) bekommen eigene
  Abschnitte im gleichen Muster: beschriftet, budgetiert, Datenblöcke
  für nicht vertrauenswürdige Inhalte.
