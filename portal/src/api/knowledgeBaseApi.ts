import { API } from '../lib/constants';
import { apiFetch, ApiError, getToken } from './client';

export interface DocumentInfo {
  id: string;
  tenant_id: string;
  collection: string;
  filename: string;
  original_name: string;
  content_type: string;
  size_bytes: number;
  chunk_count: number;
  status: string;
  created_at: number;
}

export interface CollectionInfo {
  id: string;
  name: string;
  tenant_id: string;
  description: string;
  document_count: number;
  created_at: number;
}

export interface DocumentUploadResponse {
  document_id: string;
  filename: string;
  chunk_count: number;
  status: string;
}

export const knowledgeBaseApi = {
  uploadDocument: async (
    file: File,
    tenantId: string,
    collection: string,
  ): Promise<DocumentUploadResponse> => {
    const form = new FormData();
    form.append('file', file);
    form.append('tenant_id', tenantId);
    form.append('collection', collection);

    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const res = await fetch(`${API.mcp}/api/v1/documents/upload`, {
      method: 'POST',
      headers,
      body: form,
    });

    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new ApiError(res.status, body.detail || res.statusText);
    }
    return res.json();
  },

  listDocuments: (tenantId: string, collection?: string) => {
    const params = new URLSearchParams({ tenant_id: tenantId });
    if (collection) params.set('collection', collection);
    return apiFetch<DocumentInfo[]>(`${API.mcp}/api/v1/documents?${params}`);
  },

  getDocument: (docId: string, tenantId: string) =>
    apiFetch<DocumentInfo>(`${API.mcp}/api/v1/documents/${docId}?tenant_id=${tenantId}`),

  deleteDocument: (docId: string, tenantId: string) =>
    apiFetch<void>(`${API.mcp}/api/v1/documents/${docId}?tenant_id=${tenantId}`, {
      method: 'DELETE',
    }),

  listCollections: (tenantId: string) =>
    apiFetch<CollectionInfo[]>(`${API.mcp}/api/v1/collections?tenant_id=${tenantId}`),

  createCollection: (tenantId: string, name: string, description = '') =>
    apiFetch<CollectionInfo>(`${API.mcp}/api/v1/collections`, {
      method: 'POST',
      body: JSON.stringify({ tenant_id: tenantId, name, description }),
    }),

  deleteCollection: (collectionName: string, tenantId: string) =>
    apiFetch<void>(`${API.mcp}/api/v1/collections/${collectionName}?tenant_id=${tenantId}`, {
      method: 'DELETE',
    }),
};
