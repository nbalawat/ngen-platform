import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { queryKeys } from '../../../lib/constants';
import { formatRelative } from '../../../lib/utils';
import { agentApi } from '../../../api/agentApi';
import { StatusBadge } from '../../../components/shared/StatusBadge';

type FilterTab = 'all' | 'platform' | 'custom';

export function AgentListPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<FilterTab>('all');
  const { data: agents, isLoading } = useQuery({ queryKey: queryKeys.agents.all, queryFn: agentApi.list });
  const deleteMut = useMutation({
    mutationFn: (name: string) => agentApi.delete(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.agents.all }),
  });

  const filtered = agents?.filter((a) => {
    // Source filter
    const source = (a as { source?: string }).source ?? 'tenant';
    if (filter === 'platform' && source !== 'platform') return false;
    if (filter === 'custom' && source !== 'tenant') return false;
    // Text search
    if (!search) return true;
    const q = search.toLowerCase();
    return a.name.toLowerCase().includes(q) || (a.description || '').toLowerCase().includes(q);
  });

  const platformCount = agents?.filter(a => (a as { source?: string }).source === 'platform').length ?? 0;
  const customCount = agents?.filter(a => (a as { source?: string }).source !== 'platform').length ?? 0;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Agents</h1>
          <p className="text-sm text-gray-500 mt-1">
            Platform-provided and custom agents for building workflows
          </p>
        </div>
        <Link
          to="/app/agents/new"
          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors shadow-sm"
        >
          <span>+</span> Create Agent
        </Link>
      </div>

      {/* Filter tabs + search */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex gap-1 bg-gray-100 rounded-lg p-0.5">
          {([
            { key: 'all', label: 'All', count: agents?.length ?? 0 },
            { key: 'platform', label: 'Platform', count: platformCount },
            { key: 'custom', label: 'Custom', count: customCount },
          ] as const).map(tab => (
            <button
              key={tab.key}
              onClick={() => setFilter(tab.key)}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                filter === tab.key
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab.label}
              <span className="ml-1 text-gray-400">({tab.count})</span>
            </button>
          ))}
        </div>

        {agents && agents.length > 0 && (
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search agents..."
            className="w-64 px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500"
          />
        )}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
        </div>
      ) : !filtered || filtered.length === 0 ? (
        <div className="text-center py-20 bg-white rounded-xl border border-gray-200">
          <span className="text-4xl">🧠</span>
          <h3 className="mt-3 text-lg font-medium text-gray-900">
            {search ? 'No agents match your search' : filter === 'custom' ? 'No custom agents yet' : 'No agents yet'}
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
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Source</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Invocations</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered?.map((agent) => {
                const source = (agent as { source?: string }).source ?? 'tenant';
                const isPlatform = source === 'platform';
                return (
                  <tr key={agent.name} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3">
                      <Link to={`/app/agents/${agent.name}`} className="text-sm font-medium text-blue-600 hover:text-blue-800">
                        {agent.name}
                      </Link>
                      {agent.description && (
                        <p className="text-xs text-gray-400 mt-0.5 line-clamp-1">{agent.description}</p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {isPlatform ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-700 border border-indigo-200">
                          Platform
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600 border border-gray-200">
                          Custom
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3"><StatusBadge value={agent.status} /></td>
                    <td className="px-4 py-3 text-sm text-gray-600">{agent.invocation_count}</td>
                    <td className="px-4 py-3 text-sm text-gray-500">{formatRelative(agent.created_at)}</td>
                    <td className="px-4 py-3 text-right space-x-2">
                      <Link to={`/app/agents/${agent.name}/test`} className="text-xs text-blue-600 hover:text-blue-800">
                        Test
                      </Link>
                      <Link to="/app/workflows/new" className="text-xs text-green-600 hover:text-green-800">
                        Use in Workflow
                      </Link>
                      {!isPlatform && (
                        <button
                          onClick={() => { if (confirm(`Delete agent "${agent.name}"?`)) deleteMut.mutate(agent.name); }}
                          className="text-xs text-red-500 hover:text-red-700"
                        >
                          Delete
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
