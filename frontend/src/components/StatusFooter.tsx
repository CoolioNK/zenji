/* Statusindikator im Zenji Design-System */

import type { Health } from "../types";

export function StatusFooter({ health }: { health: Health | null }) {
  const isReady = health !== null && health.ollama.available && health.model.available;

  return (
    <div className="flex items-center justify-between px-1 py-1 text-[11px] font-mono select-none">
      <div className="flex items-center gap-2">
        <span
          className={`h-2 w-2 rounded-full ${
            isReady ? "bg-accent animate-pulse-dot" : "bg-signal-amber"
          }`}
        />
        <span className="text-foreground font-medium">
          {isReady ? "System Bereit" : "Nicht verbunden"}
        </span>
      </div>
      <span className="text-[10px] text-muted-foreground uppercase tracking-wider">
        Privat
      </span>
    </div>
  );
}
