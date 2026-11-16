/* Chat-Hauptbereich inkl. Fehlerbanner (fehlendes Modell, Offline-Zustände)
   + Recherche-Live-Panel (v0.5.0). */

import { useEffect, useRef } from "react";
import { Composer } from "./Composer";
import { MessageBubble } from "./MessageBubble";
import type { ChatError, ChatResearchSummary, CommunicationModeKey, Health, Message, ResearchMode } from "../types";
import type { ResearchProgressEvent } from "../hooks/useChat";

export function ChatArea({
  messages,
  streaming,
  chatError,
  health,
  onSend,
  onStop,
  researchMode = "auto",
  onResearchModeChange,
  researchEvents = [],
  researchSummary = null,
}: {
  messages: Message[];
  streaming: boolean;
  chatError: ChatError | null;
  health: Health | null;
  onSend: (text: string, mode: CommunicationModeKey | null, research: ResearchMode) => void;
  onStop: () => void;
  researchMode?: ResearchMode;
  onResearchModeChange?: (mode: ResearchMode) => void;
  researchEvents?: ResearchProgressEvent[];
  researchSummary?: ChatResearchSummary | null;
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

          {/* Web-Recherche: echter Fortschritt + ehrliche Quellenübersicht (v0.5.0) */}
          {(researchEvents.length > 0 || researchSummary) && (
            <div className="rounded-xl border border-ink-600 bg-ink-850 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-jade-600">
                  Web-Recherche
                </span>
                {researchSummary && (
                  <span className="font-mono text-[10px] text-ink-400">
                    {researchSummary.sources.length} Quelle(n)
                    {researchSummary.contradiction_count > 0 &&
                      ` · ${researchSummary.contradiction_count} Widerspruch(e)`}
                    {researchSummary.citations_corrected > 0 &&
                      ` · ${researchSummary.citations_corrected} Marker korrigiert`}
                  </span>
                )}
              </div>

              {/* Live-Schritte (nur tatsächlich ausgeführte) */}
              <ul className="mt-2 space-y-1">
                {researchEvents.slice(-5).map((event, index) => (
                  <li key={`${index}-${event.step}`} className="flex gap-2 text-[12px] text-ink-300">
                    <span className="shrink-0 font-mono text-[10px] text-jade-600">{event.step}</span>
                    <span className="min-w-0 truncate">{event.detail}</span>
                  </li>
                ))}
              </ul>

              {/* Quellenübersicht nach Abschluss */}
              {researchSummary && researchSummary.sources.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5 border-t border-ink-700 pt-2">
                  {researchSummary.sources.map((source) => (
                    <span
                      key={`${source.marker}-${source.url}`}
                      title={source.url}
                      className="inline-flex max-w-full items-center gap-1 rounded-full border border-ink-600 bg-ink-900 px-2 py-0.5 font-mono text-[10px] text-ink-300"
                    >
                      <span className="text-jade-600">[{source.marker}]</span>
                      <span className="max-w-[220px] truncate">{source.title || source.url}</span>
                    </span>
                  ))}
                </div>
              )}
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

      <Composer
        disabled={health === null}
        streaming={streaming}
        onSend={onSend}
        onStop={onStop}
        research={researchMode}
        onResearchChange={onResearchModeChange}
      />
    </section>
  );
}
