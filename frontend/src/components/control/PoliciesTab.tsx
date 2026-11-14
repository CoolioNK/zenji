/* Control Center – Tab Policies: Regeln, Prioritäten, Konflikte. */

import { useState } from "react";
import { usePolicies } from "../../hooks/usePolicies";
import type { Policy } from "../../types";
import {
  Badge,
  Card,
  ErrorNote,
  Group,
  Hint,
  PrimaryButton,
  QuietButton,
  TextArea,
  TextField,
} from "./ui";

export function PoliciesTab() {
  const { data, loading, error, create, update, remove } = usePolicies();
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", instruction: "", priority: 50, category: "stil" });
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  if (loading && !data) {
    return <p className="text-[13px] text-ink-400">Regeln werden geladen …</p>;
  }

  const startEdit = (policy: Policy) => {
    setEditingId(policy.id);
    setForm({ name: policy.name, instruction: policy.instruction, priority: policy.priority, category: policy.category });
  };

  const saveCreate = async () => {
    setBusy(true);
    setFormError(null);
    try {
      await create(form);
      setCreating(false);
      setForm({ name: "", instruction: "", priority: 50, category: "stil" });
    } catch (exc) {
      setFormError(exc instanceof Error ? exc.message : "Anlegen fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const saveEdit = async (id: string) => {
    setBusy(true);
    setFormError(null);
    try {
      await update(id, form);
      setEditingId(null);
    } catch (exc) {
      setFormError(exc instanceof Error ? exc.message : "Speichern fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const toggleEnabled = async (policy: Policy) => {
    setBusy(true);
    setFormError(null);
    try {
      await update(policy.id, { enabled: !policy.enabled });
    } catch (exc) {
      setFormError(exc instanceof Error ? exc.message : "Änderung fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const doDelete = async (id: string) => {
    setBusy(true);
    setFormError(null);
    try {
      await remove(id);
    } catch (exc) {
      setFormError(exc instanceof Error ? exc.message : "Löschen fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const policies = data?.policies ?? [];
  const conflicts = data?.conflicts ?? [];

  return (
    <div className="space-y-6">
      {error && <ErrorNote>{error}</ErrorNote>}

      {conflicts.length > 0 && (
        <div className="rounded-xl border border-signal-amber/40 bg-signal-amber/5 px-4 py-3">
          <p className="text-[12.5px] font-medium text-signal-amber">
            {conflicts.length} Regelkonflikt(e) erkannt – höhere Priorität gewinnt:
          </p>
          <ul className="mt-1.5 space-y-1">
            {conflicts.map((conflict) => (
              <li key={`${conflict.winner_id}-${conflict.dropped_id}`} className="text-[11.5px] leading-relaxed text-ink-300">
                „{conflict.winner_name}“ verdrängt „{conflict.dropped_name}“ (Ähnlichkeit {Math.round(conflict.similarity * 100)}%).
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex items-center justify-between">
        <h3 className="text-[10px] font-semibold tracking-[0.16em] text-ink-500 uppercase">
          Regeln ({policies.length}, davon {data?.disabled_count ?? 0} deaktiviert)
        </h3>
        <button
          onClick={() => setCreating((v) => !v)}
          className="text-[12px] text-jade-500 hover:text-jade-400"
        >
          {creating ? "Abbrechen" : "+ Neue Regel"}
        </button>
      </div>

      {creating && (
        <Card>
          <div className="space-y-3">
            <Group title="Neue Regel">
              <TextField label="Name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
              <TextArea label="Anweisung" value={form.instruction} onChange={(v) => setForm({ ...form, instruction: v })} rows={3} />
              <TextField
                label={`Priorität (${form.priority})`}
                value={String(form.priority)}
                onChange={(v) => setForm({ ...form, priority: Math.max(0, Math.min(100, Number(v) || 0)) })}
              />
              <TextField label="Kategorie" value={form.category} onChange={(v) => setForm({ ...form, category: v })} />
            </Group>
            <PrimaryButton onClick={saveCreate} disabled={busy || !form.name.trim() || !form.instruction.trim()}>
              Regel anlegen
            </PrimaryButton>
          </div>
        </Card>
      )}

      {formError && <ErrorNote>{formError}</ErrorNote>}

      <div className="space-y-2">
        {policies.map((policy) => {
          const isEditing = editingId === policy.id;
          const isUser = policy.source === "user";
          return (
            <Card key={policy.id}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[13px] font-medium text-ink-50">{policy.name}</span>
                    <Badge tone={policy.priority >= 90 ? "jade" : "quiet"}>P{policy.priority}</Badge>
                    <Badge>{policy.category}</Badge>
                    <Badge>{policy.scope}</Badge>
                    {policy.source === "system" && <Badge tone="solid">System</Badge>}
                    {!policy.enabled && <Badge tone="amber">Aus</Badge>}
                  </div>
                  {isEditing ? (
                    <div className="mt-3 space-y-3">
                      <TextField label="Name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
                      <TextArea label="Anweisung" value={form.instruction} onChange={(v) => setForm({ ...form, instruction: v })} rows={3} />
                      <TextField
                        label={`Priorität (${form.priority})`}
                        value={String(form.priority)}
                        onChange={(v) => setForm({ ...form, priority: Math.max(0, Math.min(100, Number(v) || 0)) })}
                      />
                      <TextField label="Kategorie" value={form.category} onChange={(v) => setForm({ ...form, category: v })} />
                      <div className="flex gap-2">
                        <PrimaryButton onClick={() => saveEdit(policy.id)} disabled={busy}>
                          Speichern
                        </PrimaryButton>
                        <QuietButton onClick={() => setEditingId(null)}>Abbrechen</QuietButton>
                      </div>
                    </div>
                  ) : (
                    <p className="mt-1.5 text-[12px] leading-relaxed text-ink-200">{policy.instruction}</p>
                  )}
                </div>
                {!isEditing && (
                  <div className="flex shrink-0 flex-col items-end gap-1.5">
                    {isUser && (
                      <>
                        <QuietButton onClick={() => toggleEnabled(policy)} disabled={busy}>
                          {policy.enabled ? "Deaktivieren" : "Aktivieren"}
                        </QuietButton>
                        <QuietButton onClick={() => startEdit(policy)} disabled={busy}>
                          Bearbeiten
                        </QuietButton>
                        <QuietButton danger onClick={() => doDelete(policy.id)} disabled={busy}>
                          Löschen
                        </QuietButton>
                      </>
                    )}
                  </div>
                )}
              </div>
            </Card>
          );
        })}
      </div>

      <Hint>
        Systemregeln schützen Identität, Ehrlichkeit und Gedächtnis-Konsistenz. Sie sind nicht
        deaktivierbar. Nutzerregeln gelten zusätzlich und werden bei Konflikten über Priorität
        (0–100) aufgelöst.
      </Hint>
    </div>
  );
}
