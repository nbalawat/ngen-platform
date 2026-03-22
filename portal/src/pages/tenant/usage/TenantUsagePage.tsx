import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../../../lib/constants';
import { formatCost, formatTokens } from '../../../lib/utils';
import { meteringApi } from '../../../api/meteringApi';
import { tenantApi } from '../../../api/tenantApi';

export function TenantUsagePage() {
  // Get current tenant context (use first org as fallback)
  const { data: orgs } = useQuery({
    queryKey: queryKeys.orgs.all,
    queryFn: tenantApi.listOrgs,
  });
  const tenantId = orgs && orgs.length > 0 ? orgs[0].id : 'default';

  const { data: usage, isLoading } = useQuery({
    queryKey: queryKeys.usage.tenant(tenantId),
    queryFn: () => meteringApi.getUsage(tenantId),
    enabled: !!tenantId,
    refetchInterval: 15000,
  });

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Usage & Cost</h1>
        <p className="text-sm text-gray-500 mt-1">Monitor your workspace API usage and cost breakdown</p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>
      ) : !usage || (usage.total_cost === 0 && usage.total_tokens === 0 && usage.total_requests === 0) ? (
        <div className="text-center py-20 bg-white rounded-xl border border-gray-200">
          <span className="text-4xl">📊</span>
          <h3 className="mt-3 text-lg font-medium text-gray-900">No usage data yet</h3>
          <p className="mt-1 text-sm text-gray-500">Invoke agents or run workflows to see your usage here</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
              <p className="text-sm text-gray-500">Total Cost</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">{formatCost(usage.total_cost)}</p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
              <p className="text-sm text-gray-500">Total Tokens</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">{formatTokens(usage.total_tokens)}</p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
              <p className="text-sm text-gray-500">Total Requests</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">{usage.total_requests}</p>
            </div>
          </div>

          {usage.models && Object.keys(usage.models).length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm mb-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-3">Cost by Model</h2>
              <div className="space-y-2">
                {Object.entries(usage.models).map(([model, cost]) => (
                  <div key={model} className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded-lg">
                    <span className="text-sm font-medium text-gray-700">{model}</span>
                    <span className="text-sm font-semibold text-gray-900">{formatCost(cost as number)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {usage.daily_cost && Object.keys(usage.daily_cost).length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
              <h2 className="text-lg font-semibold text-gray-900 mb-3">Daily Cost</h2>
              <div className="space-y-1">
                {Object.entries(usage.daily_cost).map(([day, cost]) => (
                  <div key={day} className="flex items-center justify-between py-1.5">
                    <span className="text-sm text-gray-500">{day}</span>
                    <span className="text-sm font-medium text-gray-900">{formatCost(cost as number)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
