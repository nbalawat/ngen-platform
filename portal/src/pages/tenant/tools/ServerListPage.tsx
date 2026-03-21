import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../../../lib/constants';
import { mcpApi } from '../../../api/mcpApi';
import { StatusBadge } from '../../../components/shared/StatusBadge';

export function ServerListPage() {
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: '', endpoint: '', namespace: 'default', transport: 'streamable-http' });

  const { data: servers, isLoading } = useQuery({ queryKey: queryKeys.servers.all, queryFn: () => mcpApi.listServers() });

  const createMut = useMutation({
    mutationFn: () => mcpApi.listServers().then(() => {
      // Use raw fetch since mcpApi doesn't have createServer
      return fetch('/api/mcp/api/v1/servers', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, tools: [] }),
      }).then(r => r.json());
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: queryKeys.servers.all }); setShowCreate(false); },
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">MCP Servers</h1>
          <p className="text-sm text-gray-500 mt-1">Manage registered MCP tool servers</p>
        </div>
        <button onClick={() => setShowCreate(!showCreate)} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 shadow-sm">
          + Register Server
        </button>
      </div>

      {showCreate && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm mb-6">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">Register MCP Server</h3>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Server name" className="px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" />
            <input value={form.endpoint} onChange={(e) => setForm({ ...form, endpoint: e.target.value })} placeholder="Endpoint URL" className="px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
          <button onClick={() => createMut.mutate()} disabled={!form.name || !form.endpoint} className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm disabled:opacity-50">Register</button>
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>
      ) : !servers || servers.length === 0 ? (
        <div className="text-center py-20 bg-white rounded-xl border border-gray-200">
          <span className="text-4xl">🔌</span>
          <h3 className="mt-3 text-lg font-medium text-gray-900">No MCP servers registered</h3>
          <p className="mt-1 text-sm text-gray-500">Register an MCP server to expose tools to agents</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {servers.map((srv) => (
            <div key={srv.id} className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm hover:shadow-md transition-shadow">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold text-gray-900">{srv.name}</h3>
                <StatusBadge value={srv.status} />
              </div>
              {srv.description && <p className="text-xs text-gray-500 mb-2">{srv.description}</p>}
              <div className="text-xs text-gray-400 mb-2">
                <span>{srv.transport}</span> &middot; <span>{srv.endpoint}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">{srv.tools.length} tools</span>
                <span className="text-xs text-gray-400">{srv.namespace}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
