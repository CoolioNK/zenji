/* Einstellungen-Panel (rechte Schublade): allgemeine & provider-spezifische Parameter. */

import { useEffect, useState } from "react";
import type { Settings } from "../types";

export function SettingsPanel({
  open,
  settings,
  loading,
  saving,
  onClose,
  onLoad,
  onSave,
}: {
  open: boolean;
  settings: Settings | null;
  loading: boolean;
  saving: boolean;
  onClose: () => void;
  onLoad: () => void;
  onSave: (patch: Record<string, unknown>) => void;
}) {
  const [draft, setDraft] = useState<Settings | null>(null);

  useEffect(() => {
    if (open) void onLoad();
  }, [open, onLoad]);

  useEffect(() => {
    setDraft(settings);
  }, [settings]);

  if (!open) return null;

  const llm = draft?.llm;
  const ollama = draft?.providers.ollama;

  const save = () => {
    if (!draft) return;
    void onSave({
      llm: {
        temperature: llm?.temperature,
        top_p: llm?.top_p,
        top_k: llm?.top_k,
        repeat_penalty: llm?.repeat_penalty,
        num_predict: llm?.num_predict,
        num_ctx: llm?.num_ctx,
        stream: llm?.stream,
      },
      providers: {
        ollama: {
          base_url: ollama?.base_url,
          timeout: ollama?.timeout,
          connect_timeout: ollama?.connect_timeout,
          keep_alive: ollama?.keep_alive,
        },
      },
      persona: { system_prompt: draft.persona.system_prompt },
    });
  };

  return (
    <div className="fixed inset-y-0 right-0 z-20 flex w-[400px] flex-col border-l border-ink-700 bg-ink-850 shadow-2xl">
      <div className="flex items-center justify-between border-b border-ink-700 px-5 py-4">
        <h2 className="text-[14px] font-semibold tracking-wide text-ink-50">Einstellungen</h2>
        <button
          onClick={onClose}
          className="rounded-md px-2 py-1 text-[13px] text-ink-300 hover:bg-ink-800 hover:text-ink-50"
        >
          ✕
        </button>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto px-5 py-5">
        {loading || !draft ? (
          <p className="text-[13px] text-ink-400">Einstellungen werden geladen …</p>
        ) : (
          <>
            <Group title="Allgemeine Parameter">
              <NumberField
                label="Temperature"
                value={llm!.temperature}
                min={0}
                max={2}
                step={0.05}
                onChange={(v) => setDraft({ ...draft, llm: { ...llm!, temperature: v } })}
              />
              <NumberField
                label="Top P"
                value={llm!.top_p}
                min={0.05}
                max={1}
                step={0.05}
                onChange={(v) => setDraft({ ...draft, llm: { ...llm!, top_p: v } })}
              />
              <NumberField
                label="Top K"
                value={llm!.top_k}
                min={1}
                max={200}
                step={1}
                onChange={(v) => setDraft({ ...draft, llm: { ...llm!, top_k: Math.round(v) } })}
              />
              <NumberField
                label="Repetition Penalty"
                value={llm!.repeat_penalty}
                min={0.5}
                max={2}
                step={0.05}
                onChange={(v) => setDraft({ ...draft, llm: { ...llm!, repeat_penalty: v } })}
              />
              <NumberField
                label="Max. Output Tokens"
                value={llm!.num_predict}
                min={1}
                max={32768}
                step={128}
                onChange={(v) => setDraft({ ...draft, llm: { ...llm!, num_predict: Math.round(v) } })}
              />
              <NumberField
                label="Context Window"
                value={llm!.num_ctx}
                min={512}
                max={131072}
                step={512}
                onChange={(v) => setDraft({ ...draft, llm: { ...llm!, num_ctx: Math.round(v) } })}
              />
              <ToggleField
                label="Streaming"
                checked={llm!.stream}
                onChange={(v) => setDraft({ ...draft, llm: { ...llm!, stream: v } })}
              />
            </Group>

            <Group title="Provider: Ollama">
              <TextField
                label="Base URL"
                value={ollama!.base_url}
                onChange={(v) =>
                  setDraft({ ...draft, providers: { ollama: { ...ollama!, base_url: v } } })
                }
              />
              <NumberField
                label="Request Timeout (s)"
                value={ollama!.timeout}
                min={1}
                max={3600}
                step={5}
                onChange={(v) =>
                  setDraft({
                    ...draft,
                    providers: { ollama: { ...ollama!, timeout: v } },
                  })
                }
              />
              <TextField
                label="Keep Alive"
                value={ollama!.keep_alive}
                onChange={(v) =>
                  setDraft({ ...draft, providers: { ollama: { ...ollama!, keep_alive: v } } })
                }
              />
            </Group>

            <Group title="Persönlichkeit">
              <label className="block text-[11px] font-medium tracking-wide text-ink-300 uppercase">
                System-Prompt
              </label>
              <textarea
                rows={7}
                value={draft.persona.system_prompt}
                onChange={(e) =>
                  setDraft({ ...draft, persona: { system_prompt: e.target.value } })
                }
                className="mt-1.5 w-full resize-y rounded-lg border border-ink-600 bg-ink-900 px-3 py-2.5 text-[12.5px] leading-relaxed text-ink-100 outline-none focus:border-jade-600"
              />
            </Group>
          </>
        )}
      </div>

      <div className="border-t border-ink-700 px-5 py-4">
        <button
          onClick={save}
          disabled={saving || !draft}
          className="w-full rounded-lg bg-jade-600 py-2.5 text-[13px] font-medium text-ink-950 transition-colors hover:bg-jade-500 disabled:bg-ink-700 disabled:text-ink-400"
        >
          {saving ? "Speichern …" : "Speichern"}
        </button>
      </div>
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-3 text-[10px] font-semibold tracking-[0.16em] text-ink-500 uppercase">
        {title}
      </h3>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="flex items-center justify-between gap-4">
      <span className="text-[12.5px] text-ink-200">{label}</span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-28 rounded-lg border border-ink-600 bg-ink-900 px-2.5 py-1.5 text-right text-[12.5px] text-ink-50 outline-none focus:border-jade-600"
      />
    </label>
  );
}

function TextField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="block">
      <span className="text-[12.5px] text-ink-200">{label}</span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1.5 w-full rounded-lg border border-ink-600 bg-ink-900 px-3 py-2 text-[12.5px] text-ink-50 outline-none focus:border-jade-600"
      />
    </label>
  );
}

function ToggleField({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between gap-4">
      <span className="text-[12.5px] text-ink-200">{label}</span>
      <button
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative h-5.5 w-10 rounded-full transition-colors ${
          checked ? "bg-jade-600" : "bg-ink-600"
        }`}
      >
        <span
          className={`absolute top-0.5 h-4.5 w-4.5 rounded-full bg-ink-50 transition-all ${
            checked ? "left-[18px]" : "left-0.5"
          }`}
        />
      </button>
    </label>
  );
}
