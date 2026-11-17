/* High-End Zenji Composer im minimalistisch-japanischen Design-System */

import { useState, useRef, useEffect } from "react";
import { Send, Square } from "lucide-react";
import type { CommunicationModeKey, ResearchMode } from "../types";

export function Composer({
  disabled,
  streaming,
  onSend,
  onStop,
  research = "auto",
}: {
  disabled?: boolean;
  streaming: boolean;
  onSend: (text: string, mode: CommunicationModeKey | null, research: ResearchMode) => void;
  onStop: () => void;
  research?: ResearchMode;
}) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Automatische Anpassung der Textarea-Höhe
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const submit = () => {
    const text = value.trim();
    if (!text || disabled || streaming) return;
    // Modus und Recherche laufen automatisch; keine manuellen Dropdowns mehr.
    onSend(text, null, research);
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.focus();
    }
  };

  const hasText = value.trim().length > 0;

  return (
    <div className="relative px-4 pb-6 pt-2 bg-transparent pointer-events-none">
      <div className="mx-auto max-w-3xl pointer-events-auto">
        {/* Haupt-Eingabecontainer im fließenden Zenji-Design */}
        <div className="relative rounded-2xl border border-border/80 bg-card/85 shadow-2xl backdrop-blur-xl transition-all duration-300 focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/20 focus-within:bg-card p-3 md:p-3.5">
          <textarea
            ref={textareaRef}
            rows={1}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder="Frag Zenji etwas oder gib einen Gedanken ein …"
            disabled={disabled}
            className="w-full resize-none bg-transparent px-2 pt-1 pb-2 text-[14px] leading-relaxed text-foreground placeholder:text-muted-foreground/50 outline-none disabled:opacity-50 font-sans max-h-[200px]"
          />

          {/* Nahtlose untere Status- & Aktionsleiste ohne harte Trennlinie */}
          <div className="flex items-center justify-between pt-1 px-1">
            {/* Linke Seite: Zenji-Identität */}
            <div className="inline-flex items-center gap-2 select-none">
              <span className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-background/50 px-3 py-1 text-xs font-mono text-muted-foreground">
                <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse-dot" />
                <span className="text-foreground font-medium">Zenji Ango</span>
              </span>
            </div>

            {/* Rechte Seite: Shortcut & runder Send-Button */}
            <div className="flex items-center gap-2.5">
              <span className="hidden sm:inline font-mono text-[10px] text-muted-foreground/40 select-none">
                ↵ senden · ⇧↵ Zeile
              </span>

              {streaming ? (
                <button
                  onClick={onStop}
                  title="Generierung stoppen"
                  className="flex h-8 w-8 items-center justify-center rounded-full border border-signal-red/80 bg-card text-signal-red hover:bg-signal-red hover:text-white transition-all shadow-sm active:scale-95 cursor-pointer"
                >
                  <Square className="h-3 w-3 fill-current" />
                </button>
              ) : (
                <button
                  onClick={submit}
                  disabled={disabled || !hasText}
                  title="Senden (Enter)"
                  className={`flex h-8 w-8 items-center justify-center rounded-full transition-all duration-200 active:scale-95 shadow-sm ${
                    hasText
                      ? "bg-accent text-white hover:bg-accent/90 hover:scale-105 shadow-md shadow-accent/25 cursor-pointer"
                      : "bg-muted/70 text-muted-foreground/30 cursor-not-allowed"
                  }`}
                >
                  <Send className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}