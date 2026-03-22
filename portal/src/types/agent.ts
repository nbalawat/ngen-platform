export interface AgentInfo {
  name: string;
  description: string;
  framework: string;
  model: string;
  system_prompt: string;
  status: string;
  created_at: number;
  invocation_count: number;
}

export interface AgentCreateRequest {
  name: string;
  description?: string;
  framework?: string;
  model?: string;
  system_prompt?: string;
  metadata?: Record<string, unknown>;
}

export interface AgentInvokeRequest {
  messages: Array<{ role: string; content: string }>;
  context?: Record<string, unknown>;
  session_id?: string;
}

export interface AgentInvokeResponse {
  agent_name: string;
  events: Array<{ type: string; data: Record<string, unknown>; agent_name: string }>;
  output: string | null;
}

export interface MemoryEntry {
  id: string;
  memory_type: string;
  content: string;
  role: string | null;
  created_at: number;
}
