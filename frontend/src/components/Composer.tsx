/* Eingabebereich: autoskalierendes Textfeld, Senden/Stopp. */

import { useRef, useState } from "react";

export function Composer({
  disabled,
  streaming,
  onSend,
  onStop,
}: {
  disabled?: boolean;
  streaming: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const text = value.trim();
    if (!text || disabled || streaming) return;
    onSend(text);
    setValue("");
    textareaRef.current?.focus();
  };

  return (
    <div className="border-t border-ink-700 bg-ink-900 px-6 py-4">
      <div className="mx-auto flex max-w-3xl items-end gap-2">
        <div className="flex-1 rounded-2xl border border-ink-600 bg-ink-850 transition-colors focus-within:border-jade-600">
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
            placeholder="Nachricht an ZENJI …  (Enter senden, Shift+Enter neue Zeile)"
            disabled={disabled}
            className="max-h-[180px] w-full resize-none bg-transparent px-4 py-3 text-[14px] leading-relaxed text-ink-50 outline-none placeholder:text-ink-400 disabled:opacity-60"
          />
        </div>
        {streaming ? (
          <button
            onClick={onStop}
            title="Generierung abbrechen"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-ink-600 bg-ink-800 text-ink-200 transition-colors hover:border-signal-red hover:text-signal-red"
          >
            <span className="block h-3.5 w-3.5 rounded-[3px] bg-current" />
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={disabled || !value.trim()}
            title="Senden"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-jade-600 text-ink-950 transition-colors hover:bg-jade-500 disabled:cursor-not-allowed disabled:bg-ink-700 disabled:text-ink-400"
          >
            <svg viewBox="0 0 20 20" className="h-4.5 w-4.5" fill="currentColor" aria-hidden="true">
              <path d="M3 10 17 3l-4.2 14L9.6 11 3 10Z" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}
