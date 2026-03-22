import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../../../lib/constants';
import { formatTokens } from '../../../lib/utils';
import { memoryApi } from '../../../api/memoryApi';
import type { MemoryHealthRecommendation } from '../../../types/memory';

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

function MetricCard({ label, value, sub, icon, color }: { label: string; value: string | number; sub?: string; icon: string; color: string }) {
  return (
    <div className={`rounded-xl p-5 border shadow-sm ${color}`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium opacity-80">{label}</p>
          <p className="mt-1 text-2xl font-bold">{value}</p>
          {sub && <p className="mt-0.5 text-xs opacity-60">{sub}</p>}
        </div>
        <span className="text-2xl">{icon}</span>
      </div>
    </div>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const colors: Record<string, string> = {
    critical: 'bg-red-100 text-red-800',
    warning: 'bg-yellow-100 text-yellow-800',
    info: 'bg-blue-100 text-blue-800',
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[severity] || colors.info}`}>
      {severity}
    </span>
  );
}

export function AdminMemoryPage() {
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: queryKeys.memory.platform,
    queryFn: () => memoryApi.getPlatformStats(),
    refetchInterval: 15_000,
  });

  const { data: health } = useQuery({
    queryKey: queryKeys.memory.health,
    queryFn: () => memoryApi.getHealth(),
    refetchInterval: 30_000,
  });

  if (statsLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-orange-500" />
      </div>
    );
  }

  const agentEntries = stats ? Object.entries(stats.by_agent) : [];
  agentEntries.sort((a, b) => b[1].total_bytes - a[1].total_bytes);

  const typeEntries = stats ? Object.entries(stats.by_type) : [];
  typeEntries.sort((a, b) => b[1] - a[1]);
  const maxTypeCount = typeEntries.length > 0 ? typeEntries[0][1] : 1;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Memory Observatory</h1>
        <p className="text-sm text-gray-500 mt-1">Platform-wide memory consumption across all tenants and agents</p>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Total Entries"
          value={stats?.total_entries.toLocaleString() ?? 0}
          icon="📝"
          color="bg-blue-50 border-blue-200"
        />
        <MetricCard
          label="Total Size"
          value={formatBytes(stats?.total_bytes ?? 0)}
          icon="💾"
          color="bg-purple-50 border-purple-200"
        />
        <MetricCard
          label="Estimated Tokens"
          value={formatTokens(stats?.total_tokens ?? 0)}
          icon="🔤"
          color="bg-green-50 border-green-200"
        />
        <MetricCard
          label="Agents with Memory"
          value={stats?.agents_with_memory ?? 0}
          icon="🧠"
          color="bg-orange-50 border-orange-200"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Per-agent memory table */}
        <div className="lg:col-span-2 border rounded-lg">
          <div className="px-4 py-3 border-b bg-gray-50">
            <h2 className="font-semibold text-gray-800">Memory by Agent</h2>
          </div>
          <div className="max-h-96 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="text-left px-4 py-2 font-medium text-gray-600">Agent</th>
                  <th className="text-right px-4 py-2 font-medium text-gray-600">Entries</th>
                  <th className="text-right px-4 py-2 font-medium text-gray-600">Size</th>
                  <th className="text-right px-4 py-2 font-medium text-gray-600">Tokens</th>
                  <th className="px-4 py-2 font-medium text-gray-600 w-32"></th>
                </tr>
              </thead>
              <tbody>
                {agentEntries.map(([name, data]) => {
                  const maxBytes = agentEntries.length > 0 ? agentEntries[0][1].total_bytes : 1;
                  const pct = maxBytes > 0 ? (data.total_bytes / maxBytes) * 100 : 0;
                  return (
                    <tr key={name} className="border-t hover:bg-gray-50">
                      <td className="px-4 py-2 font-mono text-xs">{name}</td>
                      <td className="px-4 py-2 text-right">{data.total_entries}</td>
                      <td className="px-4 py-2 text-right">{formatBytes(data.total_bytes)}</td>
                      <td className="px-4 py-2 text-right">{formatTokens(data.total_tokens)}</td>
                      <td className="px-4 py-2">
                        <div className="w-full bg-gray-200 rounded-full h-2">
                          <div
                            className="bg-blue-500 h-2 rounded-full"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {agentEntries.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                      No agents have memory data yet
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Memory type distribution */}
        <div className="border rounded-lg">
          <div className="px-4 py-3 border-b bg-gray-50">
            <h2 className="font-semibold text-gray-800">By Memory Type</h2>
          </div>
          <div className="p-4 space-y-3">
            {typeEntries.map(([type, count]) => (
              <div key={type}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-gray-700">{type.replace('_', ' ')}</span>
                  <span className="font-medium">{count}</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-indigo-500 h-2 rounded-full"
                    style={{ width: `${(count / maxTypeCount) * 100}%` }}
                  />
                </div>
              </div>
            ))}
            {typeEntries.length === 0 && (
              <p className="text-sm text-gray-400 text-center py-4">No data</p>
            )}
          </div>
        </div>
      </div>

      {/* Health recommendations */}
      {health && health.recommendations.length > 0 && (
        <div className="border rounded-lg">
          <div className="px-4 py-3 border-b bg-gray-50">
            <h2 className="font-semibold text-gray-800">
              Health Recommendations
              <span className="ml-2 text-xs font-normal text-gray-500">
                {health.agents_analyzed} agents analyzed
              </span>
            </h2>
          </div>
          <div className="divide-y max-h-64 overflow-y-auto">
            {health.recommendations.map((rec: MemoryHealthRecommendation, i: number) => (
              <div key={i} className="px-4 py-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-mono text-xs text-gray-600">{rec.agent_name}</span>
                  <SeverityBadge severity={rec.severity} />
                </div>
                <p className="text-sm text-gray-800">{rec.detail}</p>
                <p className="text-xs text-gray-500 mt-1">{rec.suggestion}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
