import { apiFetch } from './client';
import { API } from '../lib/constants';
import type { MCPServer, ToolEntry, ToolCallResponse } from '../types/mcp';

export const mcpApi = {
  listServers: (namespace?: string) => {
    const params = namespace ? `?namespace=${namespace}` : '';
    return apiFetch<MCPServer[]>(`${API.mcp}/api/v1/servers${params}`);
  },
  getServer: (id: string) => apiFetch<MCPServer>(`${API.mcp}/api/v1/servers/${id}`),
  listTools: (serverName?: string, tag?: string) => {
    const params = new URLSearchParams();
    if (serverName) params.set('server_name', serverName);
    if (tag) params.set('tag', tag);
    const q = params.toString();
    return apiFetch<ToolEntry[]>(`${API.mcp}/api/v1/tools${q ? `?${q}` : ''}`);
  },
  searchTools: (query: string) => apiFetch<ToolEntry[]>(`${API.mcp}/api/v1/tools/search?q=${encodeURIComponent(query)}`),
  invoke: (serverName: string, toolName: string, args: Record<string, unknown>, namespace: string = 'default') =>
    apiFetch<ToolCallResponse>(`${API.mcp}/api/v1/invoke`, {
      method: 'POST',
      body: JSON.stringify({ server_name: serverName, tool_name: toolName, arguments: args, namespace }),
    }),
};
