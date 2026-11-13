/* Statusindikatoren (Backend, Ollama, Modell, SSD). */

import type { Health } from "../types";

function Dot({ ok, warn, label }: { ok: boolean; warn?: boolean; label: string }) {
  const color = ok
    ? "bg-jade-500"
    : warn
      ? "bg-signal-amber"
      : "bg-signal-red";
  return (
    <div className="flex items-center gap-2">
      <span
        className={`h-2 w-2 rounded-full ${color} ${ok || warn ? "animate-pulse-soft" : ""}`}
      />
      <span className="text-[11px] text-ink-300">{label}</span>
    </div>
  );
}

export function StatusFooter({ health }: { health: Health | null }) {
  const backendOk = health !== null;
  const ollamaOk = health?.ollama.available ?? false;
  const modelOk = health?.model.available ?? false;
  const storageOk = health?.storage.available ?? false;

  return (
    <div className="space-y-1.5 px-1">
      <Dot ok={backendOk} label={backendOk ? `Backend v${health?.version}` : "Backend offline"} />
      <Dot ok={ollamaOk} warn={backendOk && !ollamaOk} label={ollamaOk ? `Ollama ${health?.ollama.version ?? ""}` : "Ollama nicht erreichbar"} />
      <Dot
        ok={modelOk}
        warn={backendOk && ollamaOk && !modelOk}
        label={modelOk ? (health?.model.model ?? "Modell") : "Modell nicht geladen"}
      />
      {!storageOk && (
        <p className="rounded-md bg-ink-800 px-2.5 py-2 text-[11px] leading-relaxed text-signal-amber">
          {health?.storage.message ?? "Speicherpfad unbekannt (Backend offline)."}
        </p>
      )}
    </div>
  );
}
