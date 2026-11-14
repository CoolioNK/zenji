/* Gemeinsame Typen – Spiegelbild der Backend-Schemata. */

export type Role = "system" | "user" | "assistant";

export interface Message {
  id: string;
  conversation_id: string;
  role: Role;
  content: string;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  messages?: Message[];
}

export interface LLMSettings {
  provider: string;
  model: string;
  temperature: number;
  top_p: number;
  top_k: number;
  repeat_penalty: number;
  num_predict: number;
  num_ctx: number;
  stream: boolean;
}

export interface OllamaSettings {
  base_url: string;
  timeout: number;
  connect_timeout: number;
  keep_alive: string;
  think: boolean | null;
  strip_think: boolean;
}

export interface Settings {
  llm: LLMSettings;
  providers: { ollama: OllamaSettings };
  persona: { system_prompt: string };
}

export interface Health {
  status: "ok" | "degraded";
  version: string;
  storage: { available: boolean; root: string; message: string };
  database: { ok: boolean; path: string; message: string };
  ollama: { available: boolean; version: string | null; message: string };
  model: { model: string | null; available: boolean; message: string };
}

export interface ModelEntry {
  name: string;
  family: string | null;
  parameter_size: string | null;
  quantization: string | null;
  size_bytes: number | null;
}

export interface ApiErrorBody {
  error: { code: string; message: string; detail?: unknown };
}

/** Nutzerwählbare Darstellung eines Chat-Fehlers im Frontend. */
export interface ChatError {
  code: string;
  message: string;
}

/* ------------------------------------------------------------------ */
/* Phase 2: Control Center (Personality, Policies, Memory, Core)       */
/* ------------------------------------------------------------------ */

export interface Personality {
  id: string;
  name: string;
  identity: string;
  base_personality: string;
  communication_style: string;
  formality: number;
  humor: number;
  directness: number;
  creativity: number;
  response_length: string;
  language: string;
  situational_behavior: Record<string, string>;
  is_system: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PersonalityPreview {
  name: string;
  is_active: boolean;
  compiled_text: string;
}

export interface Policy {
  id: string;
  name: string;
  instruction: string;
  priority: number;
  enabled: boolean;
  category: string;
  scope: string;
  source: string;
  created_at: string;
  updated_at: string;
}

export interface PolicyConflict {
  winner_id: string;
  winner_name: string;
  dropped_id: string;
  dropped_name: string;
  similarity: number;
  reason: string;
}

export interface PoliciesResponse {
  policies: Policy[];
  conflicts: PolicyConflict[];
  disabled_count: number;
}

export interface Memory {
  id: string;
  content: string;
  category: string;
  memory_type: string;
  source: string;
  source_ref: string | null;
  relevance: number;
  status: string;
  supersedes_id: string | null;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface MemoryStats {
  total: number;
  active: number;
  superseded: number;
  archived: number;
  by_type: Record<string, number>;
  categories: [string, number][];
  search_provider: string;
}

export interface MemoryListResponse {
  memories: Memory[];
  stats: MemoryStats;
}

export interface MemorySearchResult {
  memory: Memory;
  score: number;
}

export interface CoreStatus {
  version: string;
  personality: string | null;
  personality_id: string | null;
  active_policies: number;
  policy_conflicts: number;
  memories: { total: number; active: number; superseded: number; archived: number };
  model: string;
  provider: string;
  num_ctx: number;
  num_predict: number;
}

export interface ContextSection {
  key: string;
  title: string;
  tokens_est: number;
  included: boolean;
  truncated: boolean;
  detail: string;
}

export interface ContextPreview {
  sections: ContextSection[];
  budget_tokens: number;
  used_tokens: number;
  usage_ratio: number;
  history_kept: number;
  history_dropped: number;
  memories_kept: number;
  memories_dropped: number;
  conflicts: number;
  flags: string[];
  system_text: string;
  messages: { role: string; content: string; chars: number }[];
  used_memory_ids: string[];
}
