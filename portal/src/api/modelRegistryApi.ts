import { apiFetch } from './client';
import { API } from '../lib/constants';
import type { ModelConfig, ModelConfigCreate } from '../types/model';

export const modelRegistryApi = {
  list: (provider?: string) => {
    const params = provider ? `?provider=${provider}` : '';
    return apiFetch<ModelConfig[]>(`${API.registry}/api/v1/models${params}`);
  },
  get: (id: string) => apiFetch<ModelConfig>(`${API.registry}/api/v1/models/${id}`),
  getByName: (name: string) => apiFetch<ModelConfig>(`${API.registry}/api/v1/models/by-name/${name}`),
  create: (data: ModelConfigCreate) => apiFetch<ModelConfig>(`${API.registry}/api/v1/models`, { method: 'POST', body: JSON.stringify(data) }),
  update: (id: string, data: Partial<ModelConfigCreate>) => apiFetch<ModelConfig>(`${API.registry}/api/v1/models/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  delete: (id: string) => apiFetch<void>(`${API.registry}/api/v1/models/${id}`, { method: 'DELETE' }),
};
