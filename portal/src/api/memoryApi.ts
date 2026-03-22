import { apiFetch } from './client';
import { API } from '../lib/constants';
import type {
  PlatformMemoryStats,
  MemoryHealthReport,
  MemoryEntry,
  TenantMemoryUsage,
  PlatformMemorySummary,
} from '../types/memory';

interface AgentMemoryStatsResponse {
  agent_name: string;
  total_entries: number;
  by_type: Record<string, { count: number; size_bytes: number; token_estimate: number }>;
  total_bytes: number;
  total_tokens: number;
  context_budget_tokens: number;
}

interface MemoryEntryListItem {
  id: string;
  memory_type: string;
  content: string;
  role: string | null;
  created_at: number;
}

export const memoryApi = {
  /** Platform-wide memory stats from workflow engine */
  getPlatformStats: (orgId?: string) =>
    apiFetch<PlatformMemoryStats>(
      `${API.workflow}/memory/stats${orgId ? `?org_id=${orgId}` : ''}`
    ),

  /** Memory health recommendations */
  getHealth: () =>
    apiFetch<MemoryHealthReport>(`${API.workflow}/memory/health`),

  /** Per-agent stats */
  getAgentStats: (name: string) =>
    apiFetch<AgentMemoryStatsResponse>(`${API.workflow}/agents/${name}/memory/stats`),

  /** Agent memory entries */
  getAgentMemory: (name: string, memoryType = 'conversational', limit = 50) =>
    apiFetch<MemoryEntryListItem[]>(
      `${API.workflow}/agents/${name}/memory?memory_type=${memoryType}&limit=${limit}`
    ),

  /** Full entry detail */
  getEntry: (agentName: string, entryId: string) =>
    apiFetch<MemoryEntry>(`${API.workflow}/agents/${agentName}/memory/${entryId}`),

  /** Per-tenant memory usage from metering service */
  getTenantMemoryUsage: (tenantId: string) =>
    apiFetch<TenantMemoryUsage>(`${API.metering}/api/v1/usage/${tenantId}/memory`),

  /** Platform-wide memory summary from metering service */
  getPlatformMemorySummary: () =>
    apiFetch<PlatformMemorySummary>(`${API.metering}/api/v1/usage/memory/summary`),
};
