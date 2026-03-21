import { apiFetch } from './client';
import { API } from '../lib/constants';
import type { AgentInfo, AgentCreateRequest, AgentInvokeRequest, AgentInvokeResponse, MemoryEntry } from '../types/agent';

export const agentApi = {
  list: () => apiFetch<AgentInfo[]>(`${API.workflow}/agents`),
  get: (name: string) => apiFetch<AgentInfo>(`${API.workflow}/agents/${name}`),
  create: (data: AgentCreateRequest) => apiFetch<AgentInfo>(`${API.workflow}/agents`, { method: 'POST', body: JSON.stringify(data) }),
  delete: (name: string) => apiFetch<void>(`${API.workflow}/agents/${name}`, { method: 'DELETE' }),
  invoke: (name: string, data: AgentInvokeRequest) => apiFetch<AgentInvokeResponse>(`${API.workflow}/agents/${name}/invoke`, { method: 'POST', body: JSON.stringify(data) }),
  getMemory: (name: string, type: string = 'conversational', limit: number = 50) =>
    apiFetch<MemoryEntry[]>(`${API.workflow}/agents/${name}/memory?memory_type=${type}&limit=${limit}`),
  getContextWindow: (name: string, query: string = '') =>
    apiFetch<{ context: string; agent_name: string }>(`${API.workflow}/agents/${name}/memory/context?query=${encodeURIComponent(query)}`),
};
