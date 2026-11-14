/* Control Center – Tab Memory: Erinnerungen einsehen, suchen, bearbeiten, löschen. */

import { useState } from "react";
import { api } from "../../services/api";
import { useMemories } from "../../hooks/useMemories";
import type { Memory } from "../../types";
import {
  Badge,
  Card,
  ErrorNote,
  Group,
  Hint,
  PrimaryButton,
  QuietButton,
  SelectField,
  SliderField,
  TextArea,
  TextField,
} from "./ui";

const TYPE_LABELS: Record<string, string> = {
  conversation: "Gespräch",
  long_term: "Langzeit",
  preference: "Präferenz",
  project: "Projekt",
};

const SOURCE_LABELS: Record<string, string> = {
  user: "Nutzer",
  chat: "Chat (Merkwort)",
};

const STATUS_LABELS: Record<string, string> = {
  active: "Aktiv",
  superseded: "Veraltet",
  archived: "Archiviert",
};

type StatusFilter = "active" | "superseded" | "archived";

export function MemoryTab() {
  const { memories, data, error, refresh, create, update, remove, search } = useMemories();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("active");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Memory[] | null>(null);
  const [scores, setScores] = useState<Record<string, number>>({});
  const [searching, setSearching] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [edit, setEdit] = useState({
    content: "",
    category: "",
    memory_type: "long_term",
    relevance: 0.5,
  });
  const [creating, setCreating] = useState(false);
  const [newMemory, setNewMemory] = useState({ content: "", memory_type: "long_term", category: "" });
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const stats = data?.stats;
  const shown: Memory[] = results ?? memories;
  const selected = shown.find((m) => m.id === selectedId) ?? null;

  const reload = async (status: StatusFilter) => {
    setStatusFilter(status);
    setResults(null);
    setScores({});
    setSelectedId(null);
    // Die Hook-Liste lädt immer aktiv; für andere Status laden wir direkt:
    if (status === "active") {
      await refresh();
    } else {
      setSearching(true);
      try {
        const response = await api.memories({ status });
        setResults(response.memories);
      } finally {
        setSearching(false);
      }
    }
  };

  const doSearch = async () => {
    if (!query.trim()) {
      setResults(null);
      setScores({});
      return;
    }
    setSearching(true);
    setFormError(null);
    try {
      const found = await search(query);
      setResults(found.map((result) => result.memory));
      const map: Record<string, number> = {};
      for (const result of found) map[result.memory.id] = result.score;
      setScores(map);
    } catch (exc) {
      setFormError(exc instanceof Error ? exc.message : "Suche fehlgeschlagen.");
    } finally {
      setSearching(false);
    }
  };

  const startEdit = (memory: Memory) => {
    setSelectedId(memory.id);
    setEdit({
      content: memory.content,
      category: memory.category,
      memory_type: memory.memory_type,
      relevance: memory.relevance,
    });
  };

  const saveEdit = async () => {
    if (!selected) return;
    setBusy(true);
    setFormError(null);
    try {
      await update(selected.id, edit);
      setResults(null);
      setSelectedId(null);
      await refresh();
    } catch (exc) {
      setFormError(exc instanceof Error ? exc.message : "Speichern fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const doDelete = async (id: string) => {
    setBusy(true);
    setFormError(null);
    try {
      await remove(id);
      setSelectedId(null);
      setResults(null);
    } catch (exc) {
      setFormError(exc instanceof Error ? exc.message : "Löschen fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const doCreate = async () => {
    setBusy(true);
    setFormError(null);
    try {
      await create(newMemory);
      setCreating(false);
      setNewMemory({ content: "", memory_type: "long_term", category: "" });
    } catch (exc) {
      setFormError(exc instanceof Error ? exc.message : "Anlegen fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      {error && <ErrorNote>{error}</ErrorNote>}

      {stats && (
        <div className="flex flex-wrap gap-2 text-[11px] text-ink-300">
          <Badge tone="jade">{stats.active} aktiv</Badge>
          <Badge tone="amber">{stats.superseded} veraltet</Badge>
          <Badge>{stats.archived} archiviert</Badge>
          <Badge>Suche: {stats.search_provider === "fts5" ? "FTS5" : "LIKE"}</Badge>
        </div>
      )}

      <div className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void doSearch();
          }}
          placeholder="Erinnerungen durchsuchen …"
          className="flex-1 rounded-lg border border-ink-600 bg-ink-900 px-3 py-2 text-[12.5px] text-ink-50 outline-none focus:border-jade-600"
        />
        <QuietButton onClick={doSearch} disabled={searching}>
          {query ? "Suchen" : "Alle"}
        </QuietButton>
      </div>

      <div className="flex gap-1.5">
        {(["active", "superseded", "archived"] as StatusFilter[]).map((status) => (
          <button
            key={status}
            onClick={() => void reload(status)}
            className={`rounded-lg px-2.5 py-1 text-[11.5px] transition-colors ${
              statusFilter === status && !results
                ? "bg-ink-800 text-ink-50"
                : "text-ink-400 hover:bg-ink-800/60 hover:text-ink-200"
            }`}
          >
            {STATUS_LABELS[status]}
          </button>
        ))}
        <button
          onClick={() => setCreating((v) => !v)}
          className="ml-auto text-[12px] text-jade-500 hover:text-jade-400"
        >
          {creating ? "Abbrechen" : "+ Erinnerung"}
        </button>
      </div>

      {creating && (
        <Card>
          <div className="space-y-3">
            <Group title="Neue Erinnerung">
              <TextArea label="Inhalt" value={newMemory.content} onChange={(v) => setNewMemory({ ...newMemory, content: v })} rows={2} />
              <SelectField
                label="Typ"
                value={newMemory.memory_type}
                onChange={(v) => setNewMemory({ ...newMemory, memory_type: v })}
                options={Object.entries(TYPE_LABELS).map(([value, label]) => ({ value, label }))}
              />
              <TextField label="Kategorie" value={newMemory.category} onChange={(v) => setNewMemory({ ...newMemory, category: v })} placeholder="z. B. Präferenz" />
            </Group>
            <PrimaryButton onClick={doCreate} disabled={busy || !newMemory.content.trim()}>
              Speichern
            </PrimaryButton>
          </div>
        </Card>
      )}

      {formError && <ErrorNote>{formError}</ErrorNote>}

      <div className="space-y-2">
        {shown.map((memory) => (
          <Card key={memory.id} selected={memory.id === selectedId}>
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge>{TYPE_LABELS[memory.memory_type] ?? memory.memory_type}</Badge>
                <Badge>{memory.category}</Badge>
                <Badge>{SOURCE_LABELS[memory.source] ?? memory.source}</Badge>
                {memory.status !== "active" && <Badge tone="amber">{STATUS_LABELS[memory.status]}</Badge>}
                {scores[memory.id] !== undefined && (
                  <Badge tone="jade">Score {Math.round(scores[memory.id] * 100)}%</Badge>
                )}
              </div>
              {memory.id === selectedId ? (
                <div className="space-y-3">
                  <TextArea label="Inhalt" value={edit.content} onChange={(v) => setEdit({ ...edit, content: v })} rows={3} />
                  <TextField label="Kategorie" value={edit.category} onChange={(v) => setEdit({ ...edit, category: v })} />
                  <SelectField
                    label="Typ"
                    value={edit.memory_type}
                    onChange={(v) => setEdit({ ...edit, memory_type: v })}
                    options={Object.entries(TYPE_LABELS).map(([value, label]) => ({ value, label }))}
                  />
                  <SliderField label="Relevanz" value={edit.relevance} onChange={(v) => setEdit({ ...edit, relevance: v })} />
                  <div className="flex gap-2">
                    <PrimaryButton onClick={saveEdit} disabled={busy}>
                      Speichern
                    </PrimaryButton>
                    <QuietButton onClick={() => setSelectedId(null)}>Abbrechen</QuietButton>
                    <QuietButton danger onClick={() => doDelete(memory.id)} disabled={busy}>
                      Löschen
                    </QuietButton>
                  </div>
                </div>
              ) : (
                <button onClick={() => startEdit(memory)} className="w-full text-left">
                  <p className="text-[12.5px] leading-relaxed text-ink-100">{memory.content}</p>
                </button>
              )}
            </div>
          </Card>
        ))}
        {shown.length === 0 && (
          <Hint>
            {results
              ? "Keine Treffer für die Suche."
              : statusFilter === "active"
                ? "Noch keine aktiven Erinnerungen. Im Chat erkannt ZENJI Merkwörter wie „Merke dir …“."
                : "Keine Einträge in dieser Kategorie."}
          </Hint>
        )}
      </div>

      {selected && (
        <Hint>
          Quelle: {SOURCE_LABELS[selected.source] ?? selected.source}
          {selected.source_ref ? ` · Bezug: ${selected.source_ref}` : ""} · Letzte Nutzung:{" "}
          {selected.last_used_at ? new Date(selected.last_used_at).toLocaleString("de-DE") : "–"}
        </Hint>
      )}
    </div>
  );
}
