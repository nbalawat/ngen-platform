import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../../lib/constants';
import { formatCost, formatTokens } from '../../lib/utils';
import { tenantApi } from '../../api/tenantApi';
import { meteringApi } from '../../api/meteringApi';
import { agentApi } from '../../api/agentApi';

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
  const usage = useQuery({ queryKey: queryKeys.usage.summary, queryFn: meteringApi.getSummary });

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Platform Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">Cross-tenant platform operations overview</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <MetricCard
          label="Total Tenants"
          value={orgs.data?.length ?? '...'}
          icon="🏢"
          color="bg-white text-gray-900 border-gray-200"
        />
        <MetricCard
          label="Active Agents"
          value={agents.data?.length ?? '...'}
          icon="🧠"
          color="bg-white text-gray-900 border-gray-200"
        />
        <MetricCard
          label="Platform Cost"
          value={usage.data ? formatCost(usage.data.total_cost) : '...'}
          sub={usage.data ? `${usage.data.total_requests} requests` : undefined}
          icon="💰"
          color="bg-white text-gray-900 border-gray-200"
        />
        <MetricCard
          label="Total Tokens"
          value={usage.data ? formatTokens(usage.data.total_tokens) : '...'}
          icon="📊"
          color="bg-white text-gray-900 border-gray-200"
        />
      </div>

      {orgs.data && orgs.data.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900 mb-3">Tenant Overview</h2>
          <table className="min-w-full divide-y divide-gray-200">
            <thead>
              <tr>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Organization</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Tier</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Max Agents</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {orgs.data.map((org) => (
                <tr key={org.id} className="hover:bg-gray-50">
                  <td className="px-3 py-2">
                    <p className="text-sm font-medium text-gray-900">{org.name}</p>
                    <p className="text-xs text-gray-400">{org.slug}</p>
                  </td>
                  <td className="px-3 py-2"><span className={`text-xs px-2 py-0.5 rounded-full font-medium ${org.tier === 'enterprise' ? 'bg-purple-100 text-purple-800' : org.tier === 'standard' ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-700'}`}>{org.tier}</span></td>
                  <td className="px-3 py-2"><span className={`text-xs px-2 py-0.5 rounded-full font-medium ${org.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>{org.status}</span></td>
                  <td className="px-3 py-2 text-sm text-gray-600">{org.max_agents}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
