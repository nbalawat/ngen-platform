import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { queryKeys, API } from '../../lib/constants';
import { formatRelative } from '../../lib/utils';
import { agentApi } from '../../api/agentApi';
import { mcpApi } from '../../api/mcpApi';
import { apiFetch } from '../../api/client';
import { StatusBadge } from '../../components/shared/StatusBadge';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface WorkflowRun {
  run_id: string;
  status: string;
  events: unknown[];
  created_at: number;
}

function StatCard({ label, value, sub, icon }: { label: string; value: string | number; sub?: string; icon: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">{label}</p>
          <p className="mt-1 text-2xl font-semibold text-gray-900">{value}</p>
          {sub && <p className="mt-0.5 text-xs text-gray-400">{sub}</p>}
        </div>
        <span className="text-2xl">{icon}</span>
      </div>
    </div>
  );
}

function QuickAction({ label, description, path, icon }: { label: string; description: string; path: string; icon: string }) {
  return (
    <Link
      to={path}
      className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm hover:shadow-md hover:border-blue-300 transition-all flex items-center gap-4"
    >
      <span className="text-3xl">{icon}</span>
      <div>
        <p className="text-sm font-semibold text-gray-900">{label}</p>
        <p className="text-xs text-gray-500">{description}</p>
      </div>
    </Link>
  );
}

export function DashboardPage() {
  const agents = useQuery({ queryKey: queryKeys.agents.all, queryFn: agentApi.list });
  const servers = useQuery({ queryKey: queryKeys.servers.all, queryFn: () => mcpApi.listServers() });
  const runs = useQuery({
    queryKey: queryKeys.workflows.runs,
    queryFn: () => apiFetch<WorkflowRun[]>(`${API.workflow}/workflows/runs`),
  });

  // Prepare chart data: invocations per agent (top 8)
  const chartData = (agents.data || [])
    .filter((a) => a.invocation_count > 0)
    .sort((a, b) => b.invocation_count - a.invocation_count)
    .slice(0, 8)
    .map((a) => ({ name: a.name.length > 12 ? a.name.slice(0, 12) + '...' : a.name, invocations: a.invocation_count }));

  const totalInvocations = (agents.data || []).reduce((s, a) => s + a.invocation_count, 0);
  const totalTools = (servers.data || []).reduce((s, srv) => s + srv.tools.length, 0);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">Your workspace overview</p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard
          label="Active Agents"
          value={agents.data?.length ?? '...'}
          sub={`${totalInvocations} total invocations`}
          icon="🧠"
        />
        <StatCard
          label="Workflow Runs"
          value={runs.data?.length ?? '...'}
          sub={runs.data ? `${runs.data.filter(r => r.status === 'completed').length} completed` : undefined}
          icon="⚡"
        />
        <StatCard
          label="MCP Servers"
          value={servers.data?.length ?? '...'}
          sub={`${totalTools} tools available`}
          icon="🔌"
        />
        <StatCard
          label="Total Tools"
          value={totalTools}
          sub="Across all servers"
          icon="🔧"
        />
      </div>

      {/* Quick Actions */}
      <div className="mb-6">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Quick Actions</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <QuickAction label="Create Agent" description="Build a new AI agent with tools and prompts" path="/app/agents/new" icon="🧠" />
          <QuickAction label="Build Workflow" description="Design a multi-agent workflow" path="/app/workflows/new" icon="⚡" />
          <QuickAction label="Explore Tools" description="Browse and test available MCP tools" path="/app/discover/tools" icon="🔧" />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Agent Activity Chart */}
        {chartData.length > 0 && (
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Agent Activity</h2>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="invocations" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Recent Workflow Runs */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Recent Workflow Runs</h2>
            <Link to="/app/workflows" className="text-xs text-blue-600 hover:text-blue-700 font-medium">View all</Link>
          </div>
          {!runs.data || runs.data.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-8">No workflow runs yet. Build and run your first workflow!</p>
          ) : (
            <div className="space-y-2">
              {runs.data.slice(0, 5).map((run) => (
                <div key={run.run_id} className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-gray-50 transition-colors">
                  <div className="flex items-center gap-3">
                    <StatusBadge value={run.status} />
                    <div>
                      <p className="text-xs font-mono text-gray-600">{run.run_id.slice(0, 8)}</p>
                      <p className="text-xs text-gray-400">{run.events.length} events</p>
                    </div>
                  </div>
                  <span className="text-xs text-gray-400">{run.created_at ? formatRelative(run.created_at) : ''}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Active Agents */}
      {agents.data && agents.data.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm mt-6">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-gray-900">Active Agents</h2>
            <Link to="/app/agents" className="text-xs text-blue-600 hover:text-blue-700 font-medium">View all</Link>
          </div>
          <div className="space-y-2">
            {agents.data.slice(0, 5).map((agent) => (
              <Link
                key={agent.name}
                to={`/app/agents/${agent.name}/test`}
                className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-gray-50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span className="text-lg">🧠</span>
                  <div>
                    <p className="text-sm font-medium text-gray-900">{agent.name}</p>
                    <p className="text-xs text-gray-500">{agent.framework} &middot; {agent.invocation_count} invocations</p>
                  </div>
                </div>
                <StatusBadge value={agent.status} />
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
