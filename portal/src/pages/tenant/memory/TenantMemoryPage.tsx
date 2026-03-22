import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../../../lib/constants';
import { formatTokens } from '../../../lib/utils';
import { memoryApi, type MemoryEntryListItem } from '../../../api/memoryApi';

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

const MEMORY_TYPES = [
  { key: 'conversational', label: 'Conversations', icon: '💬', color: 'blue' },
  { key: 'entity', label: 'Entities', icon: '🏷️', color: 'amber' },
  { key: 'summary', label: 'Summaries', icon: '📋', color: 'purple' },
  { key: 'tool_log', label: 'Tool Logs', icon: '🔧', color: 'orange' },
  { key: 'workflow', label: 'Workflow', icon: '📊', color: 'teal' },
  { key: 'toolbox', label: 'Toolbox', icon: '🧰', color: 'indigo' },
  { key: 'knowledge_base', label: 'Knowledge', icon: '📚', color: 'green' },
];

/* ── Type-specific renderers ────────────────────────────────────────── */

function ConversationalEntry({ entry }: { entry: MemoryEntry }) {
  const role = entry.role ?? 'system';
  return (
    <div className="px-4 py-3">
      <div className="flex items-center gap-2 mb-1">
        <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
          role === 'user' ? 'bg-blue-100 text-blue-700' : 'bg-green-100 text-green-700'
        }`}>
          {role}
        </span>
        <span className="text-xs text-gray-400">
          {new Date(entry.created_at * 1000).toLocaleTimeString()}
        </span>
      </div>
      <p className="text-sm text-gray-700 whitespace-pre-wrap">{entry.content}</p>
    </div>
  );
}

function EntityEntry({ entry }: { entry: MemoryEntry }) {
  const lines = entry.content.split('\n').filter(l => l.trim());
  return (
    <div className="px-4 py-3">
      <div className="flex items-center gap-2 mb-2">
        <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-700">
          entities
        </span>
        <span className="text-xs text-gray-400">
          {new Date(entry.created_at * 1000).toLocaleTimeString()}
        </span>
        {entry.metadata?.source === 'auto_extraction' && (
          <span className="text-xs text-gray-300 italic">auto-extracted</span>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {lines.map((line, i) => {
          const text = line.replace(/^[-*•]\s*/, '').trim();
          if (!text) return null;
          // Check if it's a category header (bold or ends with :)
          if (text.endsWith(':') || text.startsWith('**')) {
            return <div key={i} className="w-full text-xs font-semibold text-gray-600 mt-1">{text.replace(/\*\*/g, '')}</div>;
          }
          return (
            <span key={i} className="inline-block px-2 py-0.5 rounded-full text-xs bg-amber-50 text-amber-800 border border-amber-200">
              {text}
            </span>
          );
        })}
      </div>
    </div>
  );
}

function SummaryEntry({ entry }: { entry: MemoryEntry }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="px-4 py-3">
      <div className="flex items-center gap-2 mb-1">
        <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-700">
          summary
        </span>
        <span className="text-xs text-gray-400">
          {new Date(entry.created_at * 1000).toLocaleTimeString()}
        </span>
        <span className="text-xs text-gray-300">
          {entry.token_estimate} tokens
        </span>
      </div>
      <div className={`text-sm text-gray-700 ${!expanded ? 'line-clamp-3' : ''}`}>
        <p className="whitespace-pre-wrap">{entry.content}</p>
      </div>
      {entry.content.length > 200 && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-purple-600 hover:text-purple-800 mt-1"
        >
          {expanded ? 'Show less' : 'Show more'}
        </button>
      )}
    </div>
  );
}

function ToolLogEntry({ entry }: { entry: MemoryEntry }) {
  let parsed: Record<string, unknown> = {};
  try { parsed = JSON.parse(entry.content); } catch { /* not JSON */ }
  const toolName = String(parsed.tool ?? entry.metadata?.tool_name ?? 'unknown');
  const status = String(parsed.status ?? 'completed');

  return (
    <div className="px-4 py-3">
      <div className="flex items-center gap-2 mb-1">
        <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
          status === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
        }`}>
          {toolName}
        </span>
        <span className="text-xs text-gray-400">
          {new Date(entry.created_at * 1000).toLocaleTimeString()}
        </span>
        <span className={`text-xs ${status === 'success' ? 'text-green-500' : 'text-red-500'}`}>
          {status}
        </span>
      </div>
      <pre className="text-xs text-gray-600 bg-gray-50 rounded p-2 overflow-x-auto max-h-32 overflow-y-auto">
        {typeof parsed.output === 'string'
          ? (parsed.output as string).slice(0, 300) + ((parsed.output as string).length > 300 ? '...' : '')
          : entry.content.slice(0, 300)}
      </pre>
    </div>
  );
}

function WorkflowEntry({ entry }: { entry: MemoryEntry }) {
  return (
    <div className="px-4 py-3">
      <div className="flex items-center gap-2 mb-1">
        <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-teal-100 text-teal-700">
          state checkpoint
        </span>
        <span className="text-xs text-gray-400">
          {new Date(entry.created_at * 1000).toLocaleTimeString()}
        </span>
      </div>
      <pre className="text-xs text-gray-600 bg-gray-50 rounded p-2 overflow-x-auto max-h-24 overflow-y-auto">
        {entry.content.slice(0, 400)}
      </pre>
    </div>
  );
}

function ToolboxEntry({ entry }: { entry: MemoryEntry }) {
  const tools = (Array.isArray(entry.metadata?.tools) ? entry.metadata.tools : []) as string[];
  return (
    <div className="px-4 py-3">
      <div className="flex items-center gap-2 mb-2">
        <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-700">
          registered tools
        </span>
        <span className="text-xs text-gray-400">
          {new Date(entry.created_at * 1000).toLocaleTimeString()}
        </span>
      </div>
      {tools.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {tools.map((t, i) => (
            <span key={i} className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs bg-indigo-50 text-indigo-800 border border-indigo-200 font-mono">
              {t}
            </span>
          ))}
        </div>
      ) : (
        <p className="text-sm text-gray-600">{entry.content}</p>
      )}
    </div>
  );
}

function GenericEntry({ entry }: { entry: MemoryEntry }) {
  return (
    <div className="px-4 py-3">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs text-gray-400">
          {new Date(entry.created_at * 1000).toLocaleTimeString()}
        </span>
        <span className="text-xs text-gray-300 font-mono">{entry.id.slice(0, 8)}</span>
      </div>
      <p className="text-sm text-gray-700 line-clamp-3">{entry.content}</p>
    </div>
  );
}

type MemoryEntry = MemoryEntryListItem;

function renderEntry(entry: MemoryEntry) {
  switch (entry.memory_type) {
    case 'conversational': return <ConversationalEntry entry={entry} />;
    case 'entity': return <EntityEntry entry={entry} />;
    case 'summary': return <SummaryEntry entry={entry} />;
    case 'tool_log': return <ToolLogEntry entry={entry} />;
    case 'workflow': return <WorkflowEntry entry={entry} />;
    case 'toolbox': return <ToolboxEntry entry={entry} />;
    default: return <GenericEntry entry={entry} />;
  }
}

/* ── Main page ──────────────────────────────────────────────────────── */

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
          Inspect all 7 memory types: conversations, entities, summaries, tool logs, workflow state, toolbox, and knowledge
        </p>
      </div>

      {/* Summary cards */}
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

      {/* Type breakdown */}
      {platformStats?.by_type && (
        <div className="grid grid-cols-7 gap-2">
          {MEMORY_TYPES.map(({ key, label, icon }) => {
            const rawVal = platformStats.by_type[key];
            const count = typeof rawVal === 'number' ? rawVal : (rawVal as Record<string, number>)?.count ?? 0;
            return (
              <div key={key} className="text-center p-2 rounded border bg-gray-50">
                <span className="text-lg">{icon}</span>
                <p className="text-xs text-gray-600 mt-0.5">{label}</p>
                <p className="text-sm font-bold text-gray-800">{count}</p>
              </div>
            );
          })}
        </div>
      )}

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
              <p className="px-4 py-8 text-sm text-gray-400 text-center">No agents with memory yet</p>
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
                {MEMORY_TYPES.map(({ key, label, icon }) => {
                  const typeData = agentStats?.by_type?.[key];
                  const count = typeData?.count ?? 0;
                  return (
                    <button
                      key={key}
                      onClick={() => setSelectedType(key)}
                      className={`px-3 py-1.5 rounded text-xs whitespace-nowrap transition-colors flex items-center gap-1 ${
                        selectedType === key
                          ? 'bg-blue-100 text-blue-800 font-medium'
                          : count > 0
                            ? 'text-gray-700 hover:bg-gray-100'
                            : 'text-gray-400 hover:bg-gray-50'
                      }`}
                    >
                      <span>{icon}</span>
                      {label}
                      {count > 0 && (
                        <span className="ml-0.5 px-1 py-0 rounded-full text-[10px] bg-gray-200 text-gray-600">
                          {count}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>

              {/* Entry list with type-specific rendering */}
              <div className="max-h-[500px] overflow-y-auto divide-y">
                {entries && entries.length > 0 ? (
                  entries.map((entry: MemoryEntry) => (
                    <div key={entry.id}>{renderEntry(entry)}</div>
                  ))
                ) : (
                  <div className="flex flex-col items-center justify-center py-12 text-gray-400">
                    <span className="text-2xl mb-2">
                      {MEMORY_TYPES.find(t => t.key === selectedType)?.icon || '📝'}
                    </span>
                    <p className="text-sm">
                      No {MEMORY_TYPES.find(t => t.key === selectedType)?.label.toLowerCase() || selectedType} entries yet
                    </p>
                    <p className="text-xs text-gray-300 mt-1">
                      {selectedType === 'entity' && 'Entities are auto-extracted after agent conversations'}
                      {selectedType === 'summary' && 'Summaries are generated after 20+ conversation turns'}
                      {selectedType === 'tool_log' && 'Tool logs are recorded when agents invoke tools'}
                      {selectedType === 'toolbox' && 'Tools are registered when creating agents with tools'}
                      {selectedType === 'workflow' && 'Workflow state is captured during workflow execution'}
                    </p>
                  </div>
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
