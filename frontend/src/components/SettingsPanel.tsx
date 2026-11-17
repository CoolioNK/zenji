/* Einstellungen-Panel (rechte Schublade) – einfach für normale Nutzer */

import { useEffect, useState } from "react";
import type { Settings } from "../types";
import { X } from "lucide-react";

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

  const save = () => {
    if (!draft) return;
    void onSave({
      llm: { temperature: llm?.temperature },
      persona: { system_prompt: draft.persona.system_prompt },
    });
  };

  return (
    <div className="fixed inset-y-0 right-0 z-40 flex w-full max-w-[420px] flex-col border-l border-border bg-card shadow-2xl backdrop-blur-2xl animate-fade-up">
      <div className="flex items-center justify-between border-b border-border px-6 py-4 bg-background/60">
        <div>
          <h2 className="text-base font-semibold tracking-wide text-foreground">
            Einstellungen
          </h2>
        </div>
        <button
          onClick={onClose}
          className="flex h-7 w-7 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground hover:text-foreground hover:border-accent transition-colors"
          aria-label="Schließen"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto px-6 py-6">
        {loading || !draft ? (
          <p className="text-xs font-mono text-muted-foreground">Einstellungen werden geladen …</p>
        ) : (
          <>
            <Group title="Kreativität">
              <p className="text-[11px] text-muted-foreground mb-2">
                Wie kreativ und spontan soll Zenji antworten?
              </p>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Sachlich</span>
                <input
                  type="range"
                  min={0}
                  max={2}
                  step={0.05}
                  value={llm!.temperature}
                  onChange={(e) => setDraft({ ...draft, llm: { ...llm!, temperature: Number(e.target.value) } })}
                  className="flex-1 mx-3 accent-accent"
                />
                <span className="text-xs text-muted-foreground">Kreativ</span>
              </div>
              <p className="text-center text-xs font-mono text-muted-foreground mt-1">
                {llm!.temperature.toFixed(2)}
              </p>
            </Group>

            <Group title="Persönlichkeit">
              <p className="text-[11px] text-muted-foreground mb-2">
                Wie soll Zenji sich verhalten?
              </p>
              <textarea
                rows={8}
                value={draft.persona.system_prompt}
                onChange={(e) =>
                  setDraft({ ...draft, persona: { system_prompt: e.target.value } })
                }
                className="w-full resize-y rounded-xl border border-border bg-background p-3.5 text-xs leading-relaxed text-foreground outline-none focus:border-accent transition-colors font-sans"
              />
            </Group>
          </>
        )}
      </div>

      <div className="border-t border-border p-5 bg-background/60">
        <button
          onClick={save}
          disabled={saving || !draft}
          className="w-full rounded-full bg-primary py-2.5 text-xs font-medium text-primary-foreground transition-all duration-300 hover:bg-accent hover:text-white disabled:opacity-40 shadow-sm"
        >
          {saving ? "Wird gespeichert …" : "Speichern"}
        </button>
      </div>
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-background/50 p-4">
      <h3 className="mb-3.5 eyebrow text-accent">
        {title}
      </h3>
      <div className="space-y-3">{children}</div>
    </div>
  );
}
