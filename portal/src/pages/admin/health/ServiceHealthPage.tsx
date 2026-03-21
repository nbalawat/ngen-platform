import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../../../lib/constants';

const SERVICES = [
  { name: 'Tenant Service', url: '/api/tenant/health', port: 8000, icon: '🏢' },
  { name: 'Model Registry', url: '/api/registry/health', port: 8001, icon: '📋' },
  { name: 'Model Gateway', url: '/api/gateway/health', port: 8002, icon: '🚪' },
  { name: 'Workflow Engine', url: '/api/workflow/health', port: 8003, icon: '⚡' },
  { name: 'Governance Service', url: '/api/governance/health', port: 8004, icon: '🛡️' },
  { name: 'MCP Manager', url: '/api/mcp/health', port: 8005, icon: '🔌' },
  { name: 'Onboarding Agent', url: '/api/onboard/health', port: 8006, icon: '👋' },
  { name: 'Metering Service', url: '/api/metering/health', port: 8007, icon: '📊' },
];

async function checkAllHealth() {
  const results = await Promise.all(
    SERVICES.map(async (svc) => {
      try {
        const start = performance.now();
        const res = await fetch(svc.url);
        const latency = performance.now() - start;
        const data = await res.json();
        return { ...svc, healthy: res.ok, status: data.status, latency: Math.round(latency) };
      } catch {
        return { ...svc, healthy: false, status: 'unreachable', latency: 0 };
      }
    })
  );
  return results;
}

export function ServiceHealthPage() {
  const { data: services, isLoading } = useQuery({
    queryKey: queryKeys.health,
    queryFn: checkAllHealth,
    refetchInterval: 10000,
  });

  const allHealthy = services?.every((s) => s.healthy);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Service Health</h1>
          <p className="text-sm text-gray-500 mt-1">Real-time health monitoring of all platform services</p>
        </div>
        {services && (
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium ${allHealthy ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
            <span className={`w-2 h-2 rounded-full ${allHealthy ? 'bg-green-500' : 'bg-red-500'} animate-pulse`} />
            {allHealthy ? 'All Systems Operational' : 'Issues Detected'}
          </div>
        )}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {services?.map((svc) => (
            <div key={svc.name} className={`bg-white rounded-xl border p-5 shadow-sm transition-all ${svc.healthy ? 'border-green-200 hover:border-green-300' : 'border-red-200 hover:border-red-300'}`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">{svc.icon}</span>
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900">{svc.name}</h3>
                    <p className="text-xs text-gray-400">Port {svc.port}</p>
                  </div>
                </div>
                <div className="text-right">
                  <div className={`flex items-center gap-1.5 text-sm font-medium ${svc.healthy ? 'text-green-600' : 'text-red-600'}`}>
                    <span className={`w-2.5 h-2.5 rounded-full ${svc.healthy ? 'bg-green-500' : 'bg-red-500'}`} />
                    {svc.status}
                  </div>
                  {svc.latency > 0 && <p className="text-xs text-gray-400 mt-0.5">{svc.latency}ms</p>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
