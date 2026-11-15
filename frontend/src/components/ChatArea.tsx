/* Chat-Hauptbereich inkl. Fehlerbanner (fehlendes Modell, Offline-Zustände). */

import { useEffect, useRef } from "react";
import { Composer } from "./Composer";
import { MessageBubble } from "./MessageBubble";
import type { ChatError, CommunicationModeKey, Health, Message } from "../types";

export function ChatArea({
  messages,
  streaming,
  chatError,
  health,
  onSend,
  onStop,
}: {
  messages: Message[];
  streaming: boolean;
  chatError: ChatError | null;
  health: Health | null;
  onSend: (text: string, mode: CommunicationModeKey | null) => void;
  onStop: () => void;
}) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const modelMissing = health !== null && health.ollama.available && !health.model.available;
  const ollamaDown = health !== null && !health.ollama.available;

  return (
    <section className="flex h-full min-w-0 flex-1 flex-col bg-ink-900">
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto flex max-w-3xl flex-col gap-3">
          {(ollamaDown || modelMissing) && (
            <div className="rounded-xl border border-ink-600 bg-ink-850 px-4 py-3 text-[13px] leading-relaxed text-signal-amber">
              {ollamaDown
                ? "Ollama ist derzeit nicht erreichbar. Starte den Modellserver (./scripts/start.sh prüft dies automatisch)."
                : health?.model.message}
            </div>
          )}

          {chatError && (
            <div className="rounded-xl border border-signal-red/40 bg-ink-850 px-4 py-3 text-[13px] leading-relaxed text-signal-red">
              <span className="font-medium">Fehler ({chatError.code}):</span> {chatError.message}
            </div>
          )}

          {messages.length === 0 && !chatError && !ollamaDown && !modelMissing && (
            <div className="flex flex-col items-center pt-24 text-center">
              <svg viewBox="0 0 64 64" className="h-14 w-14 opacity-70" aria-hidden="true">
                <circle cx="32" cy="32" r="24" fill="none" stroke="#46b592" strokeWidth="4" strokeLinecap="round" strokeDasharray="132 20" transform="rotate(-70 32 32)" />
              </svg>
              <h1 className="mt-5 text-[15px] font-medium tracking-wide text-ink-100">
                Womit kann ZENJI helfen?
              </h1>
              <p className="mt-2 max-w-sm text-[12.5px] leading-relaxed text-ink-400">
                Alle Gespräche laufen lokal auf diesem Gerät.
                Konversationen werden verschlüsselt-freundlich in deiner Datenbank auf der
                externen SSD gespeichert.
              </p>
            </div>
          )}

          {messages.map((message) => (
            <MessageBubble
              key={message.id}
              message={message}
              streaming={streaming && message === messages[messages.length - 1] && message.role === "assistant"}
            />
          ))}
          <div ref={endRef} />
        </div>
      </div>

      <Composer disabled={health === null} streaming={streaming} onSend={onSend} onStop={onStop} />
    </section>
  );
}
