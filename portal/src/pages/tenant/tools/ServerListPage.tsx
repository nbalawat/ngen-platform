import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../../../lib/constants';
import { mcpApi } from '../../../api/mcpApi';
import { StatusBadge } from '../../../components/shared/StatusBadge';

export function ServerListPage() {
  const { data: servers, isLoading } = useQuery({ queryKey: queryKeys.servers.all, queryFn: () => mcpApi.listServers() });

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">MCP Servers</h1>
        <p className="text-sm text-gray-500 mt-1">Available MCP tool servers managed by the platform</p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>
      ) : !servers || servers.length === 0 ? (
        <div className="text-center py-20 bg-white rounded-xl border border-gray-200">
          <span className="text-4xl">🔌</span>
          <h3 className="mt-3 text-lg font-medium text-gray-900">No MCP servers available</h3>
          <p className="mt-1 text-sm text-gray-500">MCP servers are provisioned by the platform team and will appear here once available</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {servers.map((srv) => (
            <div key={srv.id} className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm hover:shadow-md transition-shadow">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold text-gray-900">{srv.name}</h3>
                <StatusBadge value={srv.status} />
              </div>
              {srv.description && <p className="text-xs text-gray-500 mb-2">{srv.description}</p>}
              <div className="text-xs text-gray-400 mb-2">
                <span>{srv.transport}</span> &middot; <span className="font-mono">{srv.endpoint}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-blue-600">{srv.tools.length} tools available</span>
                <span className="text-xs text-gray-400">{srv.namespace}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
