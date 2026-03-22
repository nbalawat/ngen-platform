import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { queryKeys } from '../../../lib/constants';
import { formatRelative } from '../../../lib/utils';
import { agentApi } from '../../../api/agentApi';
import { StatusBadge } from '../../../components/shared/StatusBadge';

export function AgentListPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const { data: agents, isLoading } = useQuery({ queryKey: queryKeys.agents.all, queryFn: agentApi.list });
  const deleteMut = useMutation({
    mutationFn: (name: string) => agentApi.delete(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.agents.all }),
  });

  const filtered = agents?.filter((a) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return a.name.toLowerCase().includes(q) || (a.description || '').toLowerCase().includes(q);
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Agents</h1>
          <p className="text-sm text-gray-500 mt-1">Create, test, and manage standalone AI agents</p>
        </div>
        <Link
          to="/app/agents/new"
          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors shadow-sm"
        >
          <span>+</span> Create Agent
        </Link>
      </div>

      {agents && agents.length > 0 && (
        <div className="mb-4">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search agents by name or description..."
            className="w-80 px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
        </div>
      ) : !filtered || filtered.length === 0 ? (
        <div className="text-center py-20 bg-white rounded-xl border border-gray-200">
          <span className="text-4xl">🧠</span>
          <h3 className="mt-3 text-lg font-medium text-gray-900">
            {search ? 'No agents match your search' : 'No agents yet'}
          </h3>
          <p className="mt-1 text-sm text-gray-500">
            {search ? 'Try a different search term' : 'Create your first agent to get started'}
          </p>
          <Link to="/app/agents/new" className="mt-4 inline-flex items-center text-sm text-blue-600 hover:text-blue-700">
            Create your first agent &rarr;
          </Link>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Framework</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Invocations</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered?.map((agent) => (
                <tr key={agent.name} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3">
                    <Link to={`/app/agents/${agent.name}`} className="text-sm font-medium text-blue-600 hover:text-blue-800">
                      {agent.name}
                    </Link>
                    {agent.description && <p className="text-xs text-gray-400 mt-0.5">{agent.description}</p>}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">{agent.framework}</td>
                  <td className="px-4 py-3"><StatusBadge value={agent.status} /></td>
                  <td className="px-4 py-3 text-sm text-gray-600">{agent.invocation_count}</td>
                  <td className="px-4 py-3 text-sm text-gray-500">{formatRelative(agent.created_at)}</td>
                  <td className="px-4 py-3 text-right">
                    <Link to={`/app/agents/${agent.name}/test`} className="text-xs text-blue-600 hover:text-blue-800 mr-3">
                      Test
                    </Link>
                    <button
                      onClick={() => { if (confirm(`Delete agent "${agent.name}"?`)) deleteMut.mutate(agent.name); }}
                      className="text-xs text-red-500 hover:text-red-700"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
