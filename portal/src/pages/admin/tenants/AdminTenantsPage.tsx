import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { queryKeys, API } from '../../../lib/constants';
import { formatCost, formatTokens } from '../../../lib/utils';
import { tenantApi } from '../../../api/tenantApi';
import { meteringApi } from '../../../api/meteringApi';
import { agentApi } from '../../../api/agentApi';
import { apiFetch } from '../../../api/client';
import { StatusBadge } from '../../../components/shared/StatusBadge';

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

export function AdminTenantsPage() {
  const [selectedOrg, setSelectedOrg] = useState<string | null>(null);

  const orgs = useQuery({ queryKey: queryKeys.orgs.all, queryFn: tenantApi.listOrgs });
  const allUsage = useQuery({ queryKey: ['usage', 'all'], queryFn: meteringApi.listUsage, refetchInterval: 15000 });
  const agents = useQuery({ queryKey: queryKeys.agents.all, queryFn: agentApi.list });
  const policies = useQuery({ queryKey: queryKeys.policies.all, queryFn: () => apiFetch<Policy[]>(`${API.governance}/api/v1/policies`) });
  const budgets = useQuery({ queryKey: queryKeys.budgets.all, queryFn: () => apiFetch<BudgetSpend[]>(`${API.governance}/api/v1/budgets`), refetchInterval: 15000 });

  // Build usage map by tenant_id / namespace
  const usageByTenant: Record<string, { cost: number; tokens: number; requests: number }> = {};
  for (const u of allUsage.data || []) {
    usageByTenant[u.tenant_id] = { cost: u.total_cost, tokens: u.total_tokens, requests: u.total_requests };
  }

  // Build policy count by namespace
  const policyCountByNs: Record<string, number> = {};
  for (const p of policies.data || []) {
    policyCountByNs[p.namespace] = (policyCountByNs[p.namespace] || 0) + 1;
  }

  const selectedOrgData = selectedOrg ? (orgs.data || []).find((o: any) => o.slug === selectedOrg) : null;
  const selectedUsage = selectedOrg ? usageByTenant[selectedOrg] : null;
  const selectedBudget = selectedOrg ? (budgets.data || []).find((b) => b.namespace === selectedOrg) : null;
  const selectedPolicies = selectedOrg ? (policies.data || []).filter((p) => p.namespace === selectedOrg) : [];

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Tenant Management</h1>
        <p className="text-sm text-gray-500 mt-1">Cross-tenant visibility: agents, usage, policies, and budgets per organization</p>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Tenant List */}
        <div className="col-span-2">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
            <div className="px-5 py-4 border-b border-gray-100">
              <h2 className="font-semibold text-gray-900">Organizations ({orgs.data?.length ?? 0})</h2>
              <p className="text-xs text-gray-500 mt-0.5">Click a tenant to see full activity breakdown</p>
            </div>
            <div className="overflow-auto max-h-[600px]">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">Organization</th>
                    <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">Tier</th>
                    <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                    <th className="px-4 py-2.5 text-right text-xs font-medium text-gray-500 uppercase">Cost Today</th>
                    <th className="px-4 py-2.5 text-right text-xs font-medium text-gray-500 uppercase">Tokens</th>
                    <th className="px-4 py-2.5 text-right text-xs font-medium text-gray-500 uppercase">Requests</th>
                    <th className="px-4 py-2.5 text-right text-xs font-medium text-gray-500 uppercase">Policies</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {(orgs.data || []).map((org: any) => {
                    const u = usageByTenant[org.slug];
                    const polCount = policyCountByNs[org.slug] || 0;
                    return (
                      <tr
                        key={org.id}
                        className={`cursor-pointer transition-colors ${selectedOrg === org.slug ? 'bg-blue-50' : 'hover:bg-gray-50'}`}
                        onClick={() => setSelectedOrg(selectedOrg === org.slug ? null : org.slug)}
                      >
                        <td className="px-4 py-2.5">
                          <p className="text-sm font-medium text-gray-900">{org.name}</p>
                          <p className="text-xs text-gray-400">{org.slug}</p>
                        </td>
                        <td className="px-4 py-2.5">
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${org.tier === 'ENTERPRISE' ? 'bg-purple-100 text-purple-800' : org.tier === 'STANDARD' ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-700'}`}>
                            {org.tier}
                          </span>
                        </td>
                        <td className="px-4 py-2.5"><StatusBadge value={org.status} /></td>
                        <td className="px-4 py-2.5 text-right text-sm font-mono">{u ? formatCost(u.cost) : '—'}</td>
                        <td className="px-4 py-2.5 text-right text-sm">{u ? formatTokens(u.tokens) : '—'}</td>
                        <td className="px-4 py-2.5 text-right text-sm">{u?.requests ?? '—'}</td>
                        <td className="px-4 py-2.5 text-right text-sm">{polCount || '—'}</td>
                      </tr>
                    );
                  })}
                  {(!orgs.data || orgs.data.length === 0) && (
                    <tr><td colSpan={7} className="px-4 py-10 text-center text-sm text-gray-400">No organizations registered</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* All agents across tenants */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm mt-6">
            <div className="px-5 py-4 border-b border-gray-100">
              <h2 className="font-semibold text-gray-900">All Platform Agents ({agents.data?.length ?? 0})</h2>
            </div>
            <div className="overflow-auto max-h-64">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Agent</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Framework</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                    <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">Invocations</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {(agents.data || []).map((a: any) => (
                    <tr key={a.name} className="hover:bg-gray-50">
                      <td className="px-4 py-2 text-sm font-medium text-gray-700">{a.name}</td>
                      <td className="px-4 py-2 text-sm text-gray-500">{a.framework}</td>
                      <td className="px-4 py-2"><StatusBadge value={a.status} /></td>
                      <td className="px-4 py-2 text-right text-sm">{a.invocation_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Right: Selected tenant detail */}
        <div className="space-y-5">
          {selectedOrgData ? (
            <>
              <div className="bg-blue-50 rounded-xl border border-blue-200 shadow-sm p-5">
                <h2 className="font-semibold text-blue-900 text-lg">{selectedOrgData.name}</h2>
                <p className="text-xs text-blue-600 mt-0.5">{selectedOrgData.slug} · {selectedOrgData.tier} tier</p>
                <div className="mt-3 space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-blue-700">Status</span>
                    <StatusBadge value={selectedOrgData.status} />
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-blue-700">Contact</span>
                    <span className="text-blue-900">{selectedOrgData.contact_email}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-blue-700">Max Agents</span>
                    <span className="text-blue-900">{selectedOrgData.max_agents}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-blue-700">Created</span>
                    <span className="text-blue-900">{new Date(selectedOrgData.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
              </div>

              {/* Usage for selected tenant */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
                <h3 className="font-semibold text-gray-900 mb-3">Usage Today</h3>
                {selectedUsage ? (
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm"><span className="text-gray-500">Cost</span><span className="font-mono font-medium">{formatCost(selectedUsage.cost)}</span></div>
                    <div className="flex justify-between text-sm"><span className="text-gray-500">Tokens</span><span className="font-medium">{formatTokens(selectedUsage.tokens)}</span></div>
                    <div className="flex justify-between text-sm"><span className="text-gray-500">Requests</span><span className="font-medium">{selectedUsage.requests}</span></div>
                  </div>
                ) : (
                  <p className="text-sm text-gray-400">No usage recorded today</p>
                )}
              </div>

              {/* Budget for selected tenant */}
              {selectedBudget && (
                <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
                  <h3 className="font-semibold text-gray-900 mb-3">Daily Budget</h3>
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm"><span className="text-gray-500">Date</span><span>{selectedBudget.date}</span></div>
                    <div className="flex justify-between text-sm"><span className="text-gray-500">Spend</span><span className="font-mono">{formatCost(selectedBudget.total_cost)}</span></div>
                    <div className="flex justify-between text-sm"><span className="text-gray-500">Requests</span><span>{selectedBudget.request_count}</span></div>
                    {Object.entries(selectedBudget.models).map(([m, c]) => (
                      <div key={m} className="flex justify-between text-xs"><span className="text-gray-400">{m}</span><span className="font-mono">{formatCost(c)}</span></div>
                    ))}
                  </div>
                </div>
              )}

              {/* Policies for selected tenant */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
                <h3 className="font-semibold text-gray-900 mb-3">Governance Policies ({selectedPolicies.length})</h3>
                {selectedPolicies.length > 0 ? (
                  <div className="space-y-2">
                    {selectedPolicies.map((p) => (
                      <div key={p.id} className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className={`w-1.5 h-1.5 rounded-full ${p.enabled ? 'bg-green-400' : 'bg-gray-300'}`} />
                          <span className="text-sm text-gray-700">{p.name}</span>
                        </div>
                        <span className={`text-xs px-1.5 py-0.5 rounded ${p.action === 'block' ? 'bg-red-100 text-red-600' : 'bg-yellow-100 text-yellow-600'}`}>{p.action}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-gray-400">No policies for this tenant</p>
                )}
              </div>
            </>
          ) : (
            <div className="bg-gray-50 rounded-xl border border-gray-200 p-8 text-center">
              <span className="text-3xl">🏢</span>
              <p className="text-sm text-gray-400 mt-3">Select a tenant to see full details</p>
              <p className="text-xs text-gray-400 mt-1">Including usage, budgets, and policies</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
