import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../../../lib/constants';
import { formatTokens } from '../../../lib/utils';
import { memoryApi } from '../../../api/memoryApi';

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

const MEMORY_TYPES = [
  'conversational', 'knowledge_base', 'workflow', 'toolbox', 'entity', 'summary', 'tool_log',
];

export function TenantMemoryPage() {
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [selectedType, setSelectedType] = useState('conversational');

  const { data: platformStats, isLoading } = useQuery({
    queryKey: queryKeys.memory.platform,
    queryFn: () => memoryApi.getPlatformStats(),
    refetchInterval: 10_000,
  });

  const { data: agentStats } = useQuery({
    queryKey: queryKeys.memory.agent(selectedAgent ?? ''),
    queryFn: () => memoryApi.getAgentStats(selectedAgent!),
    enabled: !!selectedAgent,
  });

  const { data: entries } = useQuery({
    queryKey: queryKeys.memory.agentEntries(selectedAgent ?? '', selectedType),
    queryFn: () => memoryApi.getAgentMemory(selectedAgent!, selectedType, 50),
    enabled: !!selectedAgent,
    refetchInterval: 5_000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }

  const agentEntries = platformStats ? Object.entries(platformStats.by_agent) : [];
  agentEntries.sort((a, b) => b[1].total_bytes - a[1].total_bytes);

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Agent Memory</h1>
        <p className="text-sm text-gray-500 mt-1">
          Inspect memory contents across your agents
        </p>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-lg border p-4 bg-blue-50 border-blue-200">
          <p className="text-sm text-blue-800">Total Entries</p>
          <p className="text-xl font-bold text-blue-900">{platformStats?.total_entries.toLocaleString() ?? 0}</p>
        </div>
        <div className="rounded-lg border p-4 bg-purple-50 border-purple-200">
          <p className="text-sm text-purple-800">Total Size</p>
          <p className="text-xl font-bold text-purple-900">{formatBytes(platformStats?.total_bytes ?? 0)}</p>
        </div>
        <div className="rounded-lg border p-4 bg-green-50 border-green-200">
          <p className="text-sm text-green-800">Est. Tokens</p>
          <p className="text-xl font-bold text-green-900">{formatTokens(platformStats?.total_tokens ?? 0)}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Agent list */}
        <div className="border rounded-lg">
          <div className="px-4 py-3 border-b bg-gray-50">
            <h2 className="font-semibold text-gray-800">Agents</h2>
          </div>
          <div className="max-h-[500px] overflow-y-auto divide-y">
            {agentEntries.map(([name, data]) => (
              <button
                key={name}
                onClick={() => setSelectedAgent(name)}
                className={`w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors ${
                  selectedAgent === name ? 'bg-blue-50 border-l-2 border-blue-500' : ''
                }`}
              >
                <p className="font-mono text-sm">{name}</p>
                <p className="text-xs text-gray-500 mt-0.5">
                  {data.total_entries} entries &middot; {formatBytes(data.total_bytes)}
                </p>
              </button>
            ))}
            {agentEntries.length === 0 && (
              <p className="px-4 py-8 text-sm text-gray-400 text-center">No agents with memory</p>
            )}
          </div>
        </div>

        {/* Memory entries viewer */}
        <div className="lg:col-span-2 border rounded-lg">
          {selectedAgent ? (
            <>
              <div className="px-4 py-3 border-b bg-gray-50 flex items-center justify-between">
                <div>
                  <h2 className="font-semibold text-gray-800">{selectedAgent}</h2>
                  {agentStats && (
                    <p className="text-xs text-gray-500">
                      {agentStats.total_entries} entries &middot; {formatBytes(agentStats.total_bytes)} &middot; {formatTokens(agentStats.total_tokens)} tokens
                    </p>
                  )}
                </div>
              </div>

              {/* Type filter tabs */}
              <div className="px-4 py-2 border-b flex gap-1 overflow-x-auto">
                {MEMORY_TYPES.map((type) => {
                  const typeData = agentStats?.by_type?.[type];
                  const count = typeData?.count ?? 0;
                  return (
                    <button
                      key={type}
                      onClick={() => setSelectedType(type)}
                      className={`px-3 py-1 rounded text-xs whitespace-nowrap transition-colors ${
                        selectedType === type
                          ? 'bg-blue-100 text-blue-800 font-medium'
                          : 'text-gray-500 hover:bg-gray-100'
                      }`}
                    >
                      {type.replace('_', ' ')}
                      {count > 0 && <span className="ml-1 text-gray-400">({count})</span>}
                    </button>
                  );
                })}
              </div>

              {/* Entry list */}
              <div className="max-h-[400px] overflow-y-auto divide-y">
                {entries && entries.length > 0 ? (
                  entries.map((entry) => (
                    <div key={entry.id} className="px-4 py-3">
                      <div className="flex items-center gap-2 mb-1">
                        {entry.role && (
                          <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                            entry.role === 'user' ? 'bg-blue-100 text-blue-700' : 'bg-green-100 text-green-700'
                          }`}>
                            {entry.role}
                          </span>
                        )}
                        <span className="text-xs text-gray-400">
                          {new Date(entry.created_at * 1000).toLocaleTimeString()}
                        </span>
                        <span className="text-xs text-gray-300 font-mono">{entry.id.slice(0, 8)}</span>
                      </div>
                      <p className="text-sm text-gray-700 line-clamp-3">{entry.content}</p>
                    </div>
                  ))
                ) : (
                  <p className="px-4 py-8 text-sm text-gray-400 text-center">
                    No {selectedType.replace('_', ' ')} entries
                  </p>
                )}
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-64 text-gray-400 text-sm">
              Select an agent to view its memory
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
