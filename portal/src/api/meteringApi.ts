import { apiFetch } from './client';
import { API } from '../lib/constants';
import type { TenantUsage, UsageSummary } from '../types/metering';

export const meteringApi = {
  listUsage: () => apiFetch<TenantUsage[]>(`${API.metering}/api/v1/usage`),
  getUsage: (tenantId: string) => apiFetch<TenantUsage>(`${API.metering}/api/v1/usage/${tenantId}`),
  getSummary: () => apiFetch<UsageSummary>(`${API.metering}/api/v1/usage/summary`),
};
