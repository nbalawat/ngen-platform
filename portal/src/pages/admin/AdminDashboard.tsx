import { useQuery } from '@tanstack/react-query';
import { queryKeys, API } from '../../lib/constants';
import { formatCost, formatTokens, formatRelative } from '../../lib/utils';
import { tenantApi } from '../../api/tenantApi';
import { meteringApi } from '../../api/meteringApi';
import { agentApi } from '../../api/agentApi';
import { apiFetch } from '../../api/client';
import type { TenantUsage } from '../../types/metering';

interface WorkflowRun {
  run_id: string;
  status: string;
  events: unknown[];
  created_at: number;
}

interface Policy {
  id: string;
  name: string;
  policy_type: string;
  namespace: string;
  action: string;
  enabled: boolean;
}

interface BudgetSpend {
  namespace: string;
  date: string | null;
  total_cost: number;
  total_tokens: number;
  request_count: number;
  models: Record<string, number>;
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

export function AdminDashboard() {
  const orgs = useQuery({ queryKey: queryKeys.orgs.all, queryFn: tenantApi.listOrgs });
  const agents = useQuery({ queryKey: queryKeys.agents.all, queryFn: agentApi.list });
  const allUsage = useQuery({ queryKey: ['usage', 'all'], queryFn: meteringApi.listUsage, refetchInterval: 10000 });
  const summary = useQuery({ queryKey: queryKeys.usage.summary, queryFn: meteringApi.getSummary, refetchInterval: 10000 });
  const runs = useQuery({ queryKey: queryKeys.workflows.runs, queryFn: () => apiFetch<WorkflowRun[]>(`${API.workflow}/workflows/runs`), refetchInterval: 10000 });
  const policies = useQuery({ queryKey: queryKeys.policies.all, queryFn: () => apiFetch<Policy[]>(`${API.governance}/api/v1/policies`) });
  const budgets = useQuery({ queryKey: queryKeys.budgets.all, queryFn: () => apiFetch<BudgetSpend[]>(`${API.governance}/api/v1/budgets`), refetchInterval: 10000 });

  // Compute aggregates
  const totalCost = allUsage.data?.reduce((s, u) => s + u.total_cost, 0) ?? 0;
  const totalTokens = allUsage.data?.reduce((s, u) => s + u.total_tokens, 0) ?? 0;
  const totalRequests = allUsage.data?.reduce((s, u) => s + u.total_requests, 0) ?? 0;
  const activeTenants = allUsage.data?.filter((u) => u.total_requests > 0).length ?? 0;
  const runningAgents = agents.data?.filter((a: any) => a.status === 'running').length ?? 0;
  const totalInvocations = agents.data?.reduce((s: number, a: any) => s + (a.invocation_count || 0), 0) ?? 0;
  const completedRuns = runs.data?.filter((r) => r.status === 'completed').length ?? 0;
  const failedRuns = runs.data?.filter((r) => r.status === 'failed').length ?? 0;
  const enabledPolicies = policies.data?.filter((p) => p.enabled).length ?? 0;

  // Per-tenant usage sorted by cost descending
  const tenantUsageSorted = [...(allUsage.data || [])].sort((a, b) => b.total_cost - a.total_cost);

  // Model breakdown across all tenants
  const modelBreakdown: Record<string, { cost: number; tenants: number }> = {};
  for (const u of allUsage.data || []) {
    for (const [model, cost] of Object.entries(u.models)) {
      if (!modelBreakdown[model]) modelBreakdown[model] = { cost: 0, tenants: 0 };
      modelBreakdown[model].cost += cost;
      modelBreakdown[model].tenants += 1;
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Platform Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">Real-time cross-tenant platform operations overview</p>
      </div>

      {/* Top-level metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <MetricCard label="Total Tenants" value={orgs.data?.length ?? '...'} sub={`${activeTenants} active today`} icon="🏢" color="bg-white text-gray-900 border-gray-200" />
        <MetricCard label="Running Agents" value={runningAgents} sub={`${totalInvocations} total invocations`} icon="🧠" color="bg-white text-gray-900 border-gray-200" />
        <MetricCard label="Platform Cost" value={formatCost(totalCost)} sub={`${totalRequests} API requests`} icon="💰" color="bg-white text-gray-900 border-gray-200" />
        <MetricCard label="Total Tokens" value={formatTokens(totalTokens)} sub={`across ${activeTenants} tenants`} icon="📊" color="bg-white text-gray-900 border-gray-200" />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <MetricCard label="Workflow Runs" value={runs.data?.length ?? '...'} sub={`${completedRuns} completed, ${failedRuns} failed`} icon="⚡" color="bg-white text-gray-900 border-gray-200" />
        <MetricCard label="Active Policies" value={enabledPolicies} sub={`${policies.data?.length ?? 0} total policies`} icon="🛡️" color="bg-white text-gray-900 border-gray-200" />
        <MetricCard label="Models in Use" value={Object.keys(modelBreakdown).length} sub={Object.keys(modelBreakdown).join(', ') || '—'} icon="🤖" color="bg-white text-gray-900 border-gray-200" />
        <MetricCard label="Budget Alerts" value={budgets.data?.filter((b) => b.total_cost > 0).length ?? 0} sub="tenants with spend today" icon="💵" color="bg-white text-gray-900 border-gray-200" />
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Per-Tenant Usage Table — main view */}
        <div className="col-span-2">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
            <div className="px-5 py-4 border-b border-gray-100">
              <h2 className="text-lg font-semibold text-gray-900">Tenant Activity</h2>
              <p className="text-xs text-gray-500 mt-0.5">Real-time usage per tenant — sorted by cost</p>
            </div>
            <div className="overflow-auto max-h-[500px]">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">Tenant</th>
                    <th className="px-4 py-2.5 text-right text-xs font-medium text-gray-500 uppercase">Cost</th>
                    <th className="px-4 py-2.5 text-right text-xs font-medium text-gray-500 uppercase">Tokens</th>
                    <th className="px-4 py-2.5 text-right text-xs font-medium text-gray-500 uppercase">Requests</th>
                    <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">Models</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {tenantUsageSorted.length === 0 ? (
                    <tr><td colSpan={5} className="px-4 py-8 text-center text-sm text-gray-400">No tenant activity yet</td></tr>
                  ) : (
                    tenantUsageSorted.map((u) => {
                      // Cost bar relative to highest
                      const maxCost = tenantUsageSorted[0]?.total_cost || 1;
                      const pct = (u.total_cost / maxCost) * 100;
                      return (
                        <tr key={u.tenant_id} className="hover:bg-gray-50">
                          <td className="px-4 py-2.5">
                            <span className="text-sm font-medium text-gray-900">{u.tenant_id}</span>
                          </td>
                          <td className="px-4 py-2.5 text-right">
                            <div className="flex items-center justify-end gap-2">
                              <div className="w-20 bg-gray-100 rounded-full h-1.5">
                                <div className="bg-blue-500 h-1.5 rounded-full" style={{ width: `${pct}%` }} />
                              </div>
                              <span className="text-sm font-mono text-gray-700">{formatCost(u.total_cost)}</span>
                            </div>
                          </td>
                          <td className="px-4 py-2.5 text-right text-sm text-gray-600">{formatTokens(u.total_tokens)}</td>
                          <td className="px-4 py-2.5 text-right text-sm text-gray-600">{u.total_requests}</td>
                          <td className="px-4 py-2.5">
                            {Object.keys(u.models).map((m) => (
                              <span key={m} className="inline-block mr-1 px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded text-xs">{m}</span>
                            ))}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Recent Workflow Runs */}
          {runs.data && runs.data.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm mt-6">
              <div className="px-5 py-4 border-b border-gray-100">
                <h2 className="text-lg font-semibold text-gray-900">Recent Workflow Runs</h2>
              </div>
              <div className="divide-y divide-gray-100">
                {runs.data.slice(0, 8).map((run) => (
                  <div key={run.run_id} className="px-5 py-3 flex items-center justify-between hover:bg-gray-50">
                    <div className="flex items-center gap-3">
                      <span className={`w-2 h-2 rounded-full ${run.status === 'completed' ? 'bg-green-400' : run.status === 'failed' ? 'bg-red-400' : run.status === 'running' ? 'bg-blue-400 animate-pulse' : 'bg-yellow-400'}`} />
                      <code className="text-xs font-mono text-gray-600">{run.run_id.slice(0, 12)}...</code>
                      <span className={`text-xs px-2 py-0.5 rounded font-medium ${run.status === 'completed' ? 'bg-green-100 text-green-700' : run.status === 'failed' ? 'bg-red-100 text-red-700' : 'bg-yellow-100 text-yellow-700'}`}>{run.status}</span>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-gray-400">
                      <span>{run.events.length} events</span>
                      <span>{formatRelative(run.created_at)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right sidebar */}
        <div className="space-y-6">
          {/* Active Agents */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
            <div className="px-5 py-4 border-b border-gray-100">
              <h2 className="font-semibold text-gray-900">Active Agents</h2>
              <p className="text-xs text-gray-500">{runningAgents} running across platform</p>
            </div>
            <div className="px-5 py-3 space-y-2 max-h-64 overflow-auto">
              {(agents.data || []).map((agent: any) => (
                <div key={agent.name} className="flex items-center justify-between py-1.5">
                  <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${agent.status === 'running' ? 'bg-green-400' : 'bg-gray-300'}`} />
                    <span className="text-sm font-medium text-gray-700">{agent.name}</span>
                  </div>
                  <div className="text-xs text-gray-400">
                    {agent.invocation_count} inv.
                  </div>
                </div>
              ))}
              {(!agents.data || agents.data.length === 0) && (
                <p className="text-sm text-gray-400 py-4 text-center">No agents registered</p>
              )}
            </div>
          </div>

          {/* Tenant Summary */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
            <div className="px-5 py-4 border-b border-gray-100">
              <h2 className="font-semibold text-gray-900">Organizations</h2>
            </div>
            <div className="px-5 py-3 space-y-2 max-h-64 overflow-auto">
              {(orgs.data || []).map((org: any) => (
                <div key={org.id} className="flex items-center justify-between py-1.5">
                  <div>
                    <span className="text-sm font-medium text-gray-700">{org.name}</span>
                    <span className="ml-2 text-xs text-gray-400">{org.slug}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${org.tier === 'ENTERPRISE' ? 'bg-purple-100 text-purple-700' : org.tier === 'STANDARD' ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-600'}`}>{org.tier}</span>
                    <span className={`w-2 h-2 rounded-full ${org.status === 'ACTIVE' ? 'bg-green-400' : 'bg-yellow-400'}`} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Governance Policies */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
            <div className="px-5 py-4 border-b border-gray-100">
              <h2 className="font-semibold text-gray-900">Governance Policies</h2>
              <p className="text-xs text-gray-500">{enabledPolicies} active across {new Set(policies.data?.map((p) => p.namespace) || []).size} namespaces</p>
            </div>
            <div className="px-5 py-3 space-y-1.5 max-h-48 overflow-auto">
              {(policies.data || []).slice(0, 10).map((p) => (
                <div key={p.id} className="flex items-center justify-between py-1">
                  <div className="flex items-center gap-2">
                    <span className={`w-1.5 h-1.5 rounded-full ${p.enabled ? 'bg-green-400' : 'bg-gray-300'}`} />
                    <span className="text-xs font-medium text-gray-700 truncate max-w-[140px]">{p.name}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-gray-400">{p.namespace}</span>
                    <span className={`text-xs px-1 py-0.5 rounded ${p.action === 'block' ? 'bg-red-100 text-red-600' : p.action === 'warn' ? 'bg-yellow-100 text-yellow-600' : 'bg-gray-100 text-gray-500'}`}>{p.action}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
