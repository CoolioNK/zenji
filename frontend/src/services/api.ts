/* Zentrale REST-Client-Wrapper für die ZENJI-API. */

import { supabase } from "../lib/supabase";
import type {
  ApiErrorBody,
  CommunicationModeKey,
  Conversation,
  Health,
  Memory,
  MemoryListResponse,
  MemorySearchResult,
  Message,
  ModelEntry,
  Personality,
  PersonalityPreview,
  PoliciesResponse,
  Policy,
  Settings,
  ContextPreview,
  CoreStatus,
  ResearchReport,
  ResearchSession,
  Source,
  SourceListResponse,
  WebSearchResponse,
  WebSettings,
  WebStatus,
} from "../types";

/* Fachlicher Fehler mit Code aus der API ({"error": {code, message}}). */
export class ApiError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

/* Basis-URL der API. Standard: /api (Dev-Proxy bzw. Cloudflare Pages Function). */
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim().replace(/\/$/, "") || "";

function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
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

/** Holt das aktuelle Supabase-Access-Token (leer, wenn nicht eingeloggt). */
async function authHeaders(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(apiUrl(path), {
    headers: { Accept: "application/json", ...(await authHeaders()) },
  });
  if (!response.ok) throw await parseError(response);
  return (await response.json()) as T;
}

export async function patchJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(apiUrl(path), {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(await authHeaders()),
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await parseError(response);
  return (await response.json()) as T;
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(apiUrl(path), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(await authHeaders()),
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await parseError(response);
  return (await response.json()) as T;
}

export async function deleteRequest<T = void>(path: string): Promise<T> {
  const response = await fetch(apiUrl(path), {
    method: "DELETE",
    headers: { Accept: "application/json", ...(await authHeaders()) },
  });
  if (!response.ok && response.status !== 204) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
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

  /* Phase 2: Control Center -------------------------------------------- */
  personalities: () => getJson<Personality[]>("/api/personality"),
  createPersonality: (body: Record<string, unknown>) =>
    postJson<Personality>("/api/personality", body),
  updatePersonality: (id: string, patch: Record<string, unknown>) =>
    patchJson<Personality>(`/api/personality/${id}`, patch),
  activatePersonality: (id: string) =>
    postJson<Personality>(`/api/personality/${id}/activate`, {}),
  deletePersonality: (id: string) => deleteRequest(`/api/personality/${id}`),
  previewPersonality: (id: string) =>
    getJson<PersonalityPreview>(`/api/personality/${id}/preview`),

  policies: () => getJson<PoliciesResponse>("/api/policies"),
  createPolicy: (body: Record<string, unknown>) =>
    postJson<Policy>("/api/policies", body),
  updatePolicy: (id: string, patch: Record<string, unknown>) =>
    patchJson<Policy>(`/api/policies/${id}`, patch),
  deletePolicy: (id: string) => deleteRequest(`/api/policies/${id}`),

  memories: (params: { memory_type?: string; category?: string; status?: string } = {}) => {
    const query = new URLSearchParams();
    if (params.memory_type) query.set("memory_type", params.memory_type);
    if (params.category) query.set("category", params.category);
    if (params.status) query.set("status", params.status);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return getJson<MemoryListResponse>(`/api/memory${suffix}`);
  },
  createMemory: (body: Record<string, unknown>) => postJson<Memory>("/api/memory", body),
  updateMemory: (id: string, patch: Record<string, unknown>) =>
    patchJson<Memory>(`/api/memory/${id}`, patch),
  deleteMemory: (id: string) => deleteRequest(`/api/memory/${id}`),
  searchMemories: (query: string, memoryType?: string, category?: string) =>
    postJson<MemorySearchResult[]>("/api/memory/search", {
      query,
      memory_type: memoryType || undefined,
      category: category || undefined,
      limit: 20,
    }),

  coreStatus: () => getJson<CoreStatus>("/api/core/status"),
  contextPreview: (message: string, conversationId?: string | null) => {
    const params = new URLSearchParams({ message });
    if (conversationId) params.set("conversation_id", conversationId);
    return getJson<ContextPreview>(`/api/core/context-preview?${params.toString()}`);
  },

  /* v0.5.0: Web Intelligence -------------------------------------------- */
  webSearch: (query: string, provider?: string, limit = 10) =>
    postJson<WebSearchResponse>("/api/web/search", {
      query,
      provider: provider || undefined,
      limit,
    }),
  webSettings: () => getJson<WebSettings>("/api/web/settings"),
  patchWebSettings: (patch: Record<string, unknown>) =>
    patchJson<WebSettings>("/api/web/settings", patch),
  webStatus: () => getJson<WebStatus>("/api/web/status"),
  clearWebCache: () => deleteRequest<{ deleted: number }>("/api/web/cache"),
  research: (question: string, mode = "standard") =>
    postJson<ResearchReport>("/api/research", { question, mode }),
  researchSessions: (limit = 50) =>
    getJson<ResearchSession[]>(`/api/research?limit=${limit}`),
  researchDetail: (id: string) =>
    getJson<ResearchSession & { plan: Record<string, unknown>; report: ResearchReport; queries: Record<string, unknown>[]; citations: Record<string, unknown>[]; error: string | null }>(`/api/research/${id}`),
  deleteResearch: (id: string) => deleteRequest(`/api/research/${id}`),
  sources: (params: { domain?: string; type?: string } = {}) => {
    const query = new URLSearchParams();
    if (params.domain) query.set("domain", params.domain);
    if (params.type) query.set("type", params.type);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return getJson<SourceListResponse>(`/api/sources${suffix}`);
  },
  source: (id: string) => getJson<Source>(`/api/sources/${id}`),
  sourceSnapshot: (id: string) =>
    getJson<{ source_id: string; content: string; content_hash: string; extractor: string; char_count: number; extracted_at: string | null }>(`/api/sources/${id}/snapshot`),
  deleteSource: (id: string) => deleteRequest(`/api/sources/${id}`),
};

/** Startet den SSE-Stream. Aufrufer liest Events via streamSSE(). */
export async function openChatStream(
  conversationId: string | null,
  message: string,
  signal?: AbortSignal,
  mode?: CommunicationModeKey | null,
  research?: string,
): Promise<Response> {
  const response = await fetch(apiUrl("/api/chat/stream"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(await authHeaders()),
    },
    body: JSON.stringify({
      conversation_id: conversationId ?? undefined,
      message,
      mode: mode || undefined,
      research: research || "auto",
    }),
    signal,
  });
  if (!response.ok) throw await parseError(response);
  return response;
}
