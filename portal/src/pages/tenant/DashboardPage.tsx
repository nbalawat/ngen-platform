import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../../lib/constants';

import { tenantApi } from '../../api/tenantApi';
import { agentApi } from '../../api/agentApi';
import { modelRegistryApi } from '../../api/modelRegistryApi';
import { mcpApi } from '../../api/mcpApi';
import { StatusBadge } from '../../components/shared/StatusBadge';

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

export function DashboardPage() {
  const orgs = useQuery({ queryKey: queryKeys.orgs.all, queryFn: tenantApi.listOrgs });
  const agents = useQuery({ queryKey: queryKeys.agents.all, queryFn: agentApi.list });
  const models = useQuery({ queryKey: queryKeys.models.all, queryFn: () => modelRegistryApi.list() });
  const servers = useQuery({ queryKey: queryKeys.servers.all, queryFn: () => mcpApi.listServers() });

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">Overview of your NGEN platform</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          label="Organizations"
          value={orgs.data?.length ?? '...'}
          icon="🏢"
        />
        <StatCard
          label="Active Agents"
          value={agents.data?.length ?? '...'}
          sub={agents.data ? `${agents.data.reduce((s, a) => s + a.invocation_count, 0)} total invocations` : undefined}
          icon="🧠"
        />
        <StatCard
          label="Registered Models"
          value={models.data?.length ?? '...'}
          icon="🤖"
        />
        <StatCard
          label="MCP Servers"
          value={servers.data?.length ?? '...'}
          sub={servers.data ? `${servers.data.reduce((s, srv) => s + srv.tools.length, 0)} tools available` : undefined}
          icon="🔌"
        />
      </div>

      {agents.data && agents.data.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm mb-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-3">Active Agents</h2>
          <div className="space-y-2">
            {agents.data.slice(0, 5).map((agent) => (
              <div key={agent.name} className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-gray-50 transition-colors">
                <div className="flex items-center gap-3">
                  <span className="text-lg">🧠</span>
                  <div>
                    <p className="text-sm font-medium text-gray-900">{agent.name}</p>
                    <p className="text-xs text-gray-500">{agent.framework} &middot; {agent.invocation_count} invocations</p>
                  </div>
                </div>
                <StatusBadge value={agent.status} />
              </div>
            ))}
          </div>
        </div>
      )}

      {models.data && models.data.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900 mb-3">Model Catalog</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {models.data.slice(0, 6).map((model) => (
              <div key={model.id} className="border border-gray-100 rounded-lg p-3 hover:border-blue-200 transition-colors">
                <div className="flex items-center justify-between mb-1">
                  <p className="text-sm font-medium text-gray-900">{model.name}</p>
                  <StatusBadge value={model.provider} />
                </div>
                <div className="flex gap-1 flex-wrap">
                  {model.capabilities.map((cap) => (
                    <span key={cap} className="text-[10px] bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded">{cap}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
