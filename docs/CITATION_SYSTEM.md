# Citation System (Belegprüfung, v0.5.0)

Antworten mit Recherche tragen **nur Beleg-Marker aus echten Quellen**.
Die Citation Engine prüft jedes `[n]` in der Antwort und entfernt
erfundene Marker – der Chat bleibt ehrlich.

## 1. Ablauf (im ChatService, nach dem LLM-Stream)

```
report.refs  →  SourceRef-Liste (Whitelist: source_id, Titel, URL,
                Domain, Typ)
Antworttext  →  CitationEngine.validate(text, refs)
             →  cleaned_text (erfundene [n] entfernt)
             →  warnings     (Liste: „Marker [5] ohne Quelle entfernt“)
```

- **Erlaubt:** Marker, die in `refs` existieren (Recherche-Quellen).
  Marker im Text bleiben stehen; Sätze mit ungültigem Marker verlieren
  nur den Marker, nicht den Inhalt (Text bleibt vollständig).
- **Warnungen** landen sichtbar im `done`-Event der SSE-Stream-Antwort
  (`research.citations_corrected` = Anzahl, `research.warnings` = Details)
  – nichts wird still „gefixt“.

## 2. Im Kontext (vor der Antwort)

- `context_block(report)` liefert FAKTEN **mit Beleg-Markern** aus echten
  Quellen – das Modell sieht die erlaubten Marker.
- `sources_block(refs)` (optional) listet die Quellen im Kontext auf.
- Zusammen ergibt das: Das Modell kennt die erlaubten Marker, und die
  Engine entfernt alles Erfundene nach dem Generieren. Doppelte Sicherheit.

## 3. Datenmodell

`citations`-Tabelle speichert je Recherche-Session die belegten Aussagen
(`statement`, `marker`, `source_id`) – Nachvollziehbarkeit auch Wochen
später über `GET /api/research/{id}`.

## 4. Grenzen (bewusst ehrlich)

- Die Engine prüft, ob ein Marker **existiert** – nicht, ob der Satz
  inhaltlich korrekt aus der Quelle stammt. Dafür stehen Quelltyp,
  Transparenz und Widerspruchsanalyse der Recherche zur Verfügung.
- Antworten ohne Recherche enthalten keine Marker-Pflicht: Ein `[n]` in
  einer Recherche-freien Antwort wird nicht entfernt (nur bei aktivem
  Report ist die Whitelist aktiv).
