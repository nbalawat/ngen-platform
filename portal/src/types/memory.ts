export interface MemoryTypeStats {
  count: number;
  size_bytes: number;
  token_estimate: number;
}

export interface AgentMemoryStats {
  total_entries: number;
  total_bytes: number;
  total_tokens: number;
  by_type: Record<string, MemoryTypeStats>;
}

export interface PlatformMemoryStats {
  total_entries: number;
  total_bytes: number;
  total_tokens: number;
  agents_with_memory: number;
  by_agent: Record<string, AgentMemoryStats>;
  by_type: Record<string, number>;
}

export interface MemoryHealthRecommendation {
  agent_name: string;
  issue: string;
  severity: 'info' | 'warning' | 'critical';
  detail: string;
  suggestion: string;
}

export interface MemoryHealthReport {
  recommendations: MemoryHealthRecommendation[];
  agents_analyzed: number;
}

export interface MemoryEntry {
  id: string;
  memory_type: string;
  content: string;
  role: string | null;
  created_at: number;
  size_bytes: number;
  token_estimate: number;
  metadata: Record<string, unknown>;
  ttl_seconds: number | null;
  summary_id: string | null;
  scope: {
    org_id: string;
    team_id: string;
    project_id: string;
    agent_name: string;
    thread_id: string | null;
  };
}

export interface TenantMemoryUsage {
  tenant_id: string;
  memory_entries: number;
  memory_bytes: number;
  memory_tokens: number;
  by_agent: Record<string, { entries: number; bytes: number; tokens: number }>;
  by_type: Record<string, number>;
}

export interface PlatformMemorySummary {
  total_memory_entries: number;
  total_memory_bytes: number;
  total_memory_tokens: number;
  tenants_with_memory: number;
  by_tenant: Record<string, { memory_entries: number; memory_bytes: number; memory_tokens: number }>;
}
