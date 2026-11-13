/* Zentrale REST-Client-Wrapper für die ZENJI-API. */

import type { ApiErrorBody, Conversation, Health, Message, ModelEntry, Settings } from "../types";

/* Fachlicher Fehler mit Code aus der API ({"error": {code, message}}). */
export class ApiError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as ApiErrorBody;
    const error = body.error;
    if (error?.message) {
      return new ApiError(error.code ?? `HTTP_${response.status}`, error.message);
    }
    return new ApiError(`HTTP_${response.status}`, `HTTP ${response.status}`);
  } catch {
    return new ApiError(`HTTP_${response.status}`, `HTTP ${response.status} ${response.statusText}`);
  }
}

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) throw await parseError(response);
  return (await response.json()) as T;
}

export async function patchJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await parseError(response);
  return (await response.json()) as T;
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await parseError(response);
  return (await response.json()) as T;
}

export async function deleteRequest(path: string): Promise<void> {
  const response = await fetch(path, { method: "DELETE" });
  if (!response.ok && response.status !== 204) throw await parseError(response);
}

/* --- Fachliche Aufrufe ------------------------------------------------- */

export const api = {
  health: () => getJson<Health>("/api/health"),
  models: () => getJson<{ provider: string; active_model: string | null; available: boolean; models: ModelEntry[] }>("/api/models"),
  settings: () => getJson<Settings>("/api/settings"),
  patchSettings: (patch: Record<string, unknown>) => patchJson<Settings>("/api/settings", patch),
  conversations: () => getJson<Conversation[]>("/api/conversations"),
  conversation: (id: string) => getJson<Conversation>(`/api/conversations/${id}`),
  renameConversation: (id: string, title: string) =>
    patchJson<Conversation>(`/api/conversations/${id}`, { title }),
  deleteConversation: (id: string) => deleteRequest(`/api/conversations/${id}`),
  chat: (conversationId: string | null, message: string) =>
    postJson<{ conversation_id: string; user_message: Message; assistant_message: Message }>(
      "/api/chat",
      { conversation_id: conversationId ?? undefined, message },
    ),
};

/** Startet den SSE-Stream. Aufrufer liest Events via streamSSE(). */
export async function openChatStream(
  conversationId: string | null,
  message: string,
  signal?: AbortSignal,
): Promise<Response> {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ conversation_id: conversationId ?? undefined, message }),
    signal,
  });
  if (!response.ok) throw await parseError(response);
  return response;
}
