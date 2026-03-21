import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { meteringApi } from '../../../api/meteringApi';
import { formatCost, formatTokens } from '../../../lib/utils';
import type { TenantUsage } from '../../../types/metering';

export function AdminUsagePage() {
  const [selectedTenant, setSelectedTenant] = useState<string | null>(null);

  const { data: allUsage, isLoading } = useQuery({
    queryKey: ['usage', 'all'],
    queryFn: meteringApi.listUsage,
    refetchInterval: 10000,
  });

  const sorted = [...(allUsage || [])].sort((a, b) => b.total_cost - a.total_cost);
  const totalCost = sorted.reduce((s, u) => s + u.total_cost, 0);
  const totalTokens = sorted.reduce((s, u) => s + u.total_tokens, 0);
  const totalRequests = sorted.reduce((s, u) => s + u.total_requests, 0);

  // Model breakdown across all tenants
  const modelTotals: Record<string, { cost: number; tokens: number; requests: number; tenants: Set<string> }> = {};
  for (const u of sorted) {
    for (const [model, cost] of Object.entries(u.models)) {
      if (!modelTotals[model]) modelTotals[model] = { cost: 0, tokens: 0, requests: 0, tenants: new Set() };
      modelTotals[model].cost += cost;
      modelTotals[model].tenants.add(u.tenant_id);
    }
  }

  const detail = selectedTenant ? sorted.find((u) => u.tenant_id === selectedTenant) : null;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Usage Analytics</h1>
        <p className="text-sm text-gray-500 mt-1">Cross-tenant token consumption, cost breakdown, and API activity</p>
      </div>

      {/* Platform totals */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <p className="text-xs text-gray-500">Total Platform Cost</p>
          <p className="text-xl font-bold text-gray-900 mt-1">{formatCost(totalCost)}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <p className="text-xs text-gray-500">Total Tokens Consumed</p>
          <p className="text-xl font-bold text-gray-900 mt-1">{formatTokens(totalTokens)}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <p className="text-xs text-gray-500">Total API Requests</p>
          <p className="text-xl font-bold text-gray-900 mt-1">{totalRequests}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <p className="text-xs text-gray-500">Active Tenants</p>
          <p className="text-xl font-bold text-gray-900 mt-1">{sorted.length}</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Per-tenant usage */}
        <div className="col-span-2">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
            <div className="px-5 py-4 border-b border-gray-100">
              <h2 className="font-semibold text-gray-900">Per-Tenant Usage</h2>
              <p className="text-xs text-gray-500 mt-0.5">Click a tenant to see detailed breakdown</p>
            </div>
            {isLoading ? (
              <div className="flex justify-center py-10"><div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600" /></div>
            ) : (
              <div className="overflow-auto max-h-[500px]">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase">Tenant</th>
                      <th className="px-4 py-2.5 text-right text-xs font-medium text-gray-500 uppercase">Cost</th>
                      <th className="px-4 py-2.5 text-right text-xs font-medium text-gray-500 uppercase">Tokens</th>
                      <th className="px-4 py-2.5 text-right text-xs font-medium text-gray-500 uppercase">Requests</th>
                      <th className="px-4 py-2.5 text-right text-xs font-medium text-gray-500 uppercase">% of Total</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {sorted.map((u) => {
                      const pct = totalCost > 0 ? ((u.total_cost / totalCost) * 100).toFixed(1) : '0.0';
                      return (
                        <tr
                          key={u.tenant_id}
                          className={`cursor-pointer transition-colors ${selectedTenant === u.tenant_id ? 'bg-blue-50' : 'hover:bg-gray-50'}`}
                          onClick={() => setSelectedTenant(selectedTenant === u.tenant_id ? null : u.tenant_id)}
                        >
                          <td className="px-4 py-2.5">
                            <span className="text-sm font-medium text-gray-900">{u.tenant_id}</span>
                          </td>
                          <td className="px-4 py-2.5 text-right text-sm font-mono text-gray-700">{formatCost(u.total_cost)}</td>
                          <td className="px-4 py-2.5 text-right text-sm text-gray-600">{formatTokens(u.total_tokens)}</td>
                          <td className="px-4 py-2.5 text-right text-sm text-gray-600">{u.total_requests}</td>
                          <td className="px-4 py-2.5 text-right">
                            <div className="flex items-center justify-end gap-2">
                              <div className="w-16 bg-gray-100 rounded-full h-1.5">
                                <div className="bg-blue-500 h-1.5 rounded-full" style={{ width: `${pct}%` }} />
                              </div>
                              <span className="text-xs text-gray-500 w-10 text-right">{pct}%</span>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Right: Detail + Model breakdown */}
        <div className="space-y-6">
          {/* Selected tenant detail */}
          {detail ? (
            <div className="bg-white rounded-xl border border-blue-200 shadow-sm">
              <div className="px-5 py-4 border-b border-blue-100 bg-blue-50 rounded-t-xl">
                <h2 className="font-semibold text-blue-900">{detail.tenant_id}</h2>
                <p className="text-xs text-blue-700 mt-0.5">Tenant detail breakdown</p>
              </div>
              <div className="p-5 space-y-3">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Total Cost</span>
                  <span className="font-mono font-medium">{formatCost(detail.total_cost)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Total Tokens</span>
                  <span className="font-medium">{formatTokens(detail.total_tokens)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">API Requests</span>
                  <span className="font-medium">{detail.total_requests}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Avg Cost/Request</span>
                  <span className="font-mono">{detail.total_requests > 0 ? formatCost(detail.total_cost / detail.total_requests) : '—'}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Avg Tokens/Request</span>
                  <span>{detail.total_requests > 0 ? Math.round(detail.total_tokens / detail.total_requests) : '—'}</span>
                </div>
                <hr className="border-gray-200" />
                <h4 className="text-xs font-semibold text-gray-500 uppercase">Models Used</h4>
                {Object.entries(detail.models).map(([model, cost]) => (
                  <div key={model} className="flex justify-between text-sm">
                    <span className="text-gray-700">{model}</span>
                    <span className="font-mono text-gray-600">{formatCost(cost)}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="bg-gray-50 rounded-xl border border-gray-200 p-5 text-center">
              <p className="text-sm text-gray-400">Click a tenant row to see detailed breakdown</p>
            </div>
          )}

          {/* Model breakdown */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
            <div className="px-5 py-4 border-b border-gray-100">
              <h2 className="font-semibold text-gray-900">Model Usage</h2>
              <p className="text-xs text-gray-500">Cross-tenant model breakdown</p>
            </div>
            <div className="p-5 space-y-3">
              {Object.entries(modelTotals).map(([model, data]) => (
                <div key={model} className="flex items-center justify-between">
                  <div>
                    <span className="text-sm font-medium text-gray-700">{model}</span>
                    <span className="ml-2 text-xs text-gray-400">{data.tenants.size} tenants</span>
                  </div>
                  <span className="text-sm font-mono text-gray-600">{formatCost(data.cost)}</span>
                </div>
              ))}
              {Object.keys(modelTotals).length === 0 && (
                <p className="text-sm text-gray-400 text-center py-4">No model usage yet</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
