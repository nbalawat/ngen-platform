import { apiFetch } from './client';
import { API } from '../lib/constants';
import type { Policy, EvalResult } from '../types/governance';

export const governanceApi = {
  listPolicies: (namespace?: string, type?: string) => {
    const params = new URLSearchParams();
    if (namespace) params.set('namespace', namespace);
    if (type) params.set('type', type);
    const q = params.toString();
    return apiFetch<Policy[]>(`${API.governance}/api/v1/policies${q ? `?${q}` : ''}`);
  },
  getPolicy: (id: string) => apiFetch<Policy>(`${API.governance}/api/v1/policies/${id}`),
  createPolicy: (data: Record<string, unknown>) => apiFetch<Policy>(`${API.governance}/api/v1/policies`, { method: 'POST', body: JSON.stringify(data) }),
  updatePolicy: (id: string, data: Record<string, unknown>) => apiFetch<Policy>(`${API.governance}/api/v1/policies/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deletePolicy: (id: string) => apiFetch<void>(`${API.governance}/api/v1/policies/${id}`, { method: 'DELETE' }),
  evaluate: (context: Record<string, unknown>) => apiFetch<EvalResult>(`${API.governance}/api/v1/evaluate`, { method: 'POST', body: JSON.stringify(context) }),
  getBudget: (namespace: string) => apiFetch<Record<string, unknown>>(`${API.governance}/api/v1/budgets/${namespace}`),
  listBudgets: () => apiFetch<Record<string, unknown>[]>(`${API.governance}/api/v1/budgets`),
};
