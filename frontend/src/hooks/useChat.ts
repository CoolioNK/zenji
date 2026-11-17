/* Chat-Zustand: Nachrichten laden, senden, streamen, abbrechen. */

import { useCallback, useEffect, useRef, useState } from "react";
import { api, openChatStream, ApiError } from "../services/api";
import { streamSSE } from "../services/sse";
import type {
  ChatError,
  ChatResearchSummary,
  CommunicationModeKey,
  Message,
  ResearchMode,
  ResearchProgressEvent,
} from "../types";

export type ChatStatus = "idle" | "loading-history" | "streaming";

export interface ChatState {
  messages: Message[];
  status: ChatStatus;
  error: ChatError | null;
  send: (text: string, mode?: CommunicationModeKey | null, research?: ResearchMode) => Promise<void>;
  stop: () => void;
}

export function useChat(
  conversationId: string | null,
  onConversationCreated: (id: string) => void,
): ChatState {
  const [messages, setMessages] = useState<Message[]>([]);
  const [status, setStatus] = useState<ChatStatus>("idle");
  const [error, setError] = useState<ChatError | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  /* Läuft gerade ein Senden, darf der Verlauflader die lokalen
     Nachrichten nicht löschen (Sonst-Race: conversation_id wechselt
     beim Start-Event null → id und die Deltas würden verworfen). */
  const inFlightRef = useRef(false);

  /* Verlauf laden, wenn eine Konversation gewählt wird. */
  useEffect(() => {
    let cancelled = false;
    if (inFlightRef.current) return; // Stream in Arbeit: Zustand behalten

    setError(null);
    setMessages([]);

    if (conversationId === null) {
      setStatus("idle");
      return;
    }
    setStatus("loading-history");
    api
      .conversation(conversationId)
      .then((detail) => {
        if (!cancelled) setMessages(detail.messages ?? []);
      })
      .catch((exc: unknown) => {
        if (!cancelled) {
          setError({ code: "LOAD_FAILED", message: exc instanceof Error ? exc.message : "Verlauf konnte nicht geladen werden." });
        }
      })
      .finally(() => {
        if (!cancelled) setStatus("idle");
      });

    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const send = useCallback(
    async (text: string, mode?: CommunicationModeKey | null, research?: ResearchMode) => {
      const trimmed = text.trim();
      if (!trimmed || status === "streaming") return;
      setError(null);

      /* Optimistische Nutzernachricht (Wird durch Server-Objekt ersetzt). */
      const localUser: Message = {
        id: `local-${Date.now()}`,
        conversation_id: conversationId ?? "",
        role: "user",
        content: trimmed,
        created_at: new Date().toISOString(),
      };
      const streamingId = `stream-${Date.now()}`;
      const localAssistant: Message = {
        id: streamingId,
        conversation_id: conversationId ?? "",
        role: "assistant",
        content: "",
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, localUser, localAssistant]);
      setStatus("streaming");

      const controller = new AbortController();
      abortRef.current = controller;
      inFlightRef.current = true;
      const isNewConversation = conversationId === null;

      const appendTo = (id: string, delta: string) => {
        setMessages((prev) =>
          prev.map((m) => (m.id === id ? { ...m, content: m.content + delta } : m)),
        );
      };
      const finalize = (id: string, serverId: string | null, content: string) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === id
              ? { ...m, id: serverId ?? m.id, content, conversation_id: conversationId ?? m.conversation_id }
              : m,
          ),
        );
      };

      try {
        const response = await openChatStream(
          conversationId,
          trimmed,
          controller.signal,
          mode ?? null,
          research ?? "auto",
        );
        let createdConversationId: string | null = conversationId;
        let serverUserId: string | null = null;

        for await (const sse of streamSSE(response)) {
          if (sse.event === "start") {
            createdConversationId = (sse.data.conversation_id as string) ?? createdConversationId;
            serverUserId = (sse.data.user_message_id as string) ?? null;
            if (conversationId === null && createdConversationId) {
              onConversationCreated(createdConversationId);
            }
          } else if (sse.event === "research") {
            /* Echtes Recherche-Ereignis direkt an die laufende Assistant-Antwort hängen. */
            const researchEvent = sse.data as ResearchProgressEvent;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === streamingId
                  ? { ...m, researchEvents: [...(m.researchEvents ?? []), researchEvent] }
                  : m,
              ),
            );
          } else if (sse.event === "delta") {
            appendTo(streamingId, (sse.data.content as string) ?? "");
          } else if (sse.event === "done") {
            const summary = (sse.data.research as ChatResearchSummary | undefined) ?? null;
            if (summary) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === streamingId ? { ...m, researchSummary: summary } : m,
                ),
              );
            }
            finalize(
              streamingId,
              (sse.data.assistant_message_id as string) ?? null,
              (sse.data.content as string) ?? "",
            );
            if (isNewConversation && createdConversationId) {
              /* Konversationsliste aktualisieren (Nachrichtenzähler). */
              onConversationCreated(createdConversationId);
            }
          } else if (sse.event === "error") {
            throw new StreamedError(
              (sse.data.code as string) ?? "LLM_ERROR",
              (sse.data.message as string) ?? "Unbekannter Fehler während des Streams.",
            );
          }
        }

        /* Server-IDs übernehmen (Nutzer-Nachricht). */
        if (serverUserId) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === localUser.id
                ? {
                    ...m,
                    id: serverUserId as string,
                    conversation_id: createdConversationId ?? m.conversation_id,
                  }
                : m,
            ),
          );
        }
      } catch (exc) {
        if (exc instanceof DOMException && exc.name === "AbortError") {
          /* Vom Nutzer abgebrochen: Teilantwort bleibt stehen. */
          setMessages((prev) => prev.filter((m) => m.content !== "" || m.role === "user"));
        } else if (exc instanceof StreamedError) {
          setError({ code: exc.code, message: exc.message });
          /* Leere Streaming-Bubble entfernen. */
          setMessages((prev) => prev.filter((m) => !(m.id === streamingId && m.content === "")));
        } else {
          setError({
            code: exc instanceof ApiError ? exc.code : "CHAT_FAILED",
            message: exc instanceof Error ? exc.message : "Die Nachricht konnte nicht gesendet werden.",
          });
          setMessages((prev) => prev.filter((m) => !(m.id === streamingId && m.content === "")));
        }
      } finally {
        abortRef.current = null;
        inFlightRef.current = false;
        setStatus("idle");
      }
    },
    [conversationId, onConversationCreated, status],
  );

  return { messages, status, error, send, stop };
}

class StreamedError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}
