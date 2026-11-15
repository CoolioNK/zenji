/* Control Center – Tab Personality: Profile ansehen, bearbeiten, aktivieren. */

import { useEffect, useMemo, useState } from "react";
import { api } from "../../services/api";
import { usePersonalities } from "../../hooks/usePersonalities";
import type { Personality, PersonalityPreview } from "../../types";
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

interface Draft {
  name: string;
  identity: string;
  communication_style: string;
  formality: number;
  humor: number;
  sarcasm: number;
  cheekiness: number;
  directness: number;
  friendliness: number;
  empathy: number;
  curiosity: number;
  initiative: number;
  creativity: number;
  response_length: string;
  language: string;
  behavior_lines: string;
}

function draftFrom(profile: Personality): Draft {
  const behavior = Object.entries(profile.situational_behavior ?? {}).map(
    ([situation, conduct]) => `${situation}: ${conduct}`,
  );
  return {
    name: profile.name,
    identity: profile.identity,
    communication_style: profile.communication_style,
    formality: profile.formality,
    humor: profile.humor,
    sarcasm: profile.sarcasm ?? 0.3,
    cheekiness: profile.cheekiness ?? 0.4,
    directness: profile.directness,
    friendliness: profile.friendliness ?? 0.7,
    empathy: profile.empathy ?? 0.6,
    curiosity: profile.curiosity ?? 0.6,
    initiative: profile.initiative ?? 0.5,
    creativity: profile.creativity,
    response_length: profile.response_length,
    language: profile.language,
    behavior_lines: behavior.join("\n"),
  };
}

function parseBehavior(lines: string): Record<string, string> {
  const map: Record<string, string> = {};
  for (const line of lines.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const separator = trimmed.indexOf(":");
    if (separator <= 0) continue;
    const situation = trimmed.slice(0, separator).trim();
    const conduct = trimmed.slice(separator + 1).trim();
    if (situation && conduct) map[situation] = conduct;
  }
  return map;
}

export function PersonalityTab() {
  const { profiles, loading, error, refresh, create, update, activate, remove } =
    usePersonalities();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newIdentity, setNewIdentity] = useState("");
  const [preview, setPreview] = useState<PersonalityPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const selected = useMemo(
    () => profiles.find((p) => p.id === selectedId) ?? null,
    [profiles, selectedId],
  );

  useEffect(() => {
    setDraft(selected ? draftFrom(selected) : null);
    setPreview(null);
  }, [selected]);

  if (loading && profiles.length === 0) {
    return <p className="text-[13px] text-ink-400">Profile werden geladen …</p>;
  }

  const save = async () => {
    if (!selected || !draft) return;
    setBusy(true);
    setFormError(null);
    try {
      await update(selected.id, {
        name: draft.name,
        identity: draft.identity,
        communication_style: draft.communication_style,
        formality: draft.formality,
        humor: draft.humor,
        sarcasm: draft.sarcasm,
        cheekiness: draft.cheekiness,
        directness: draft.directness,
        friendliness: draft.friendliness,
        empathy: draft.empathy,
        curiosity: draft.curiosity,
        initiative: draft.initiative,
        creativity: draft.creativity,
        response_length: draft.response_length,
        language: draft.language,
        situational_behavior: parseBehavior(draft.behavior_lines),
      });
      await refresh();
    } catch (exc) {
      setFormError(exc instanceof Error ? exc.message : "Speichern fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const doActivate = async () => {
    if (!selected) return;
    setBusy(true);
    setFormError(null);
    try {
      await activate(selected.id);
      await refresh();
    } catch (exc) {
      setFormError(exc instanceof Error ? exc.message : "Aktivieren fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const doDelete = async () => {
    if (!selected) return;
    setBusy(true);
    setFormError(null);
    try {
      await remove(selected.id);
      setSelectedId(null);
    } catch (exc) {
      setFormError(exc instanceof Error ? exc.message : "Löschen fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const doPreview = async () => {
    if (!selected) return;
    setBusy(true);
    setFormError(null);
    try {
      setPreview(await api.previewPersonality(selected.id));
    } catch (exc) {
      setFormError(exc instanceof Error ? exc.message : "Vorschau fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  const doCreate = async () => {
    setBusy(true);
    setFormError(null);
    try {
      const profile = await create({
        name: newName,
        identity: newIdentity,
        base_personality: "custom",
      });
      setCreating(false);
      setNewName("");
      setNewIdentity("");
      setSelectedId(profile.id);
    } catch (exc) {
      setFormError(exc instanceof Error ? exc.message : "Anlegen fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      {error && <ErrorNote>{error}</ErrorNote>}

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-[10px] font-semibold tracking-[0.16em] text-ink-500 uppercase">
            Profile
          </h3>
          <button
            onClick={() => setCreating((v) => !v)}
            className="text-[12px] text-jade-500 hover:text-jade-400"
          >
            {creating ? "Abbrechen" : "+ Neues Profil"}
          </button>
        </div>

        {creating && (
          <Card>
            <div className="space-y-3">
              <TextField label="Name" value={newName} onChange={setNewName} placeholder="z. B. Mentor" />
              <TextArea
                label="Identität"
                value={newIdentity}
                onChange={setNewIdentity}
                rows={2}
                placeholder="Du bist ZENJI als …"
              />
              <PrimaryButton onClick={doCreate} disabled={busy || !newName.trim()}>
                Profil anlegen
              </PrimaryButton>
            </div>
          </Card>
        )}

        {profiles.map((profile) => (
          <Card key={profile.id} selected={profile.id === selectedId}>
            <button
              onClick={() => setSelectedId(profile.id)}
              className="w-full text-left"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-[13px] font-medium text-ink-50">{profile.name}</span>
                <span className="flex gap-1.5">
                  {profile.is_active && <Badge tone="jade">Aktiv</Badge>}
                  {profile.is_system && <Badge>System</Badge>}
                </span>
              </div>
              <p className="mt-1 line-clamp-2 text-[11.5px] leading-relaxed text-ink-400">
                {profile.communication_style || profile.identity || profile.base_personality}
              </p>
            </button>
          </Card>
        ))}
      </div>

      {formError && <ErrorNote>{formError}</ErrorNote>}

      {selected && draft && (
        <div className="space-y-5 border-t border-ink-700 pt-5">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[13px] font-semibold text-ink-50">
              Bearbeiten: {selected.name}
            </h3>
            <Badge>{selected.base_personality}</Badge>
          </div>

          <Group title="Identität & Stil">
            <TextArea label="Identität" value={draft.identity} onChange={(v) => setDraft({ ...draft, identity: v })} rows={3} />
            <TextField
              label="Kommunikationsstil"
              value={draft.communication_style}
              onChange={(v) => setDraft({ ...draft, communication_style: v })}
              placeholder="z. B. sachlich, strukturiert"
            />
          </Group>

          <Group title="Eigenschaften">
            <SliderField label="Formalität" value={draft.formality} onChange={(v) => setDraft({ ...draft, formality: v })} />
            <SliderField label="Humor" value={draft.humor} onChange={(v) => setDraft({ ...draft, humor: v })} />
            <SliderField label="Sarkasmus" value={draft.sarcasm} onChange={(v) => setDraft({ ...draft, sarcasm: v })} />
            <SliderField label="Frechheit" value={draft.cheekiness} onChange={(v) => setDraft({ ...draft, cheekiness: v })} />
            <SliderField label="Direktheit" value={draft.directness} onChange={(v) => setDraft({ ...draft, directness: v })} />
            <SliderField label="Freundlichkeit" value={draft.friendliness} onChange={(v) => setDraft({ ...draft, friendliness: v })} />
            <SliderField label="Empathie" value={draft.empathy} onChange={(v) => setDraft({ ...draft, empathy: v })} />
            <SliderField label="Neugier" value={draft.curiosity} onChange={(v) => setDraft({ ...draft, curiosity: v })} />
            <SliderField label="Eigeninitiative" value={draft.initiative} onChange={(v) => setDraft({ ...draft, initiative: v })} />
            <SliderField label="Kreativität" value={draft.creativity} onChange={(v) => setDraft({ ...draft, creativity: v })} />
            <SelectField
              label="Antwortlänge"
              value={draft.response_length}
              onChange={(v) => setDraft({ ...draft, response_length: v })}
              options={[
                { value: "short", label: "Kurz" },
                { value: "balanced", label: "Ausgewogen" },
                { value: "detailed", label: "Ausführlich" },
              ]}
            />
            <SelectField
              label="Sprache"
              value={draft.language}
              onChange={(v) => setDraft({ ...draft, language: v })}
              options={[
                { value: "auto", label: "Sprache des Nutzers" },
                { value: "de", label: "Immer Deutsch" },
                { value: "en", label: "Immer Englisch" },
              ]}
            />
          </Group>

          <Group title="Situationsverhalten">
            <TextArea
              label="Situation: Verhalten (eine pro Zeile)"
              value={draft.behavior_lines}
              onChange={(v) => setDraft({ ...draft, behavior_lines: v })}
              rows={4}
              placeholder={"Fehler oder Unsicherheit: ehrlich sagen, was unklar ist."}
            />
            <Hint>
              Zeilen im Format „Situation: Verhalten“. Sie landen als Abschnitt im Persönlichkeitskontext.
            </Hint>
          </Group>

          <div className="flex flex-wrap gap-2">
            <PrimaryButton onClick={save} disabled={busy}>
              Änderungen speichern
            </PrimaryButton>
            <QuietButton onClick={doActivate} disabled={busy || selected.is_active}>
              {selected.is_active ? "Ist aktiv" : "Aktivieren"}
            </QuietButton>
            <QuietButton onClick={doPreview} disabled={busy}>
              Vorschau
            </QuietButton>
            <QuietButton
              danger
              onClick={doDelete}
              disabled={busy || selected.is_system || selected.is_active}
            >
              Löschen
            </QuietButton>
          </div>

          {preview && (
            <div className="rounded-xl border border-ink-700 bg-ink-900 px-4 py-3">
              <p className="mb-2 text-[10px] font-semibold tracking-[0.16em] text-ink-500 uppercase">
                Kompilierter Persönlichkeitskontext
              </p>
              <pre className="whitespace-pre-wrap font-mono text-[11.5px] leading-relaxed text-ink-200">
                {preview.compiled_text}
              </pre>
            </div>
          )}

          {selected.is_system && (
            <Hint>
              Systemprofile können bearbeitet werden, aber nicht gelöscht werden.
            </Hint>
          )}
        </div>
      )}

      {!selected && !creating && profiles.length > 0 && (
        <Hint>Wähle ein Profil, um es zu bearbeiten oder zu aktivieren.</Hint>
      )}
    </div>
  );
}
