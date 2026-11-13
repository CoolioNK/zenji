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
