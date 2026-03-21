import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TenantShell, AdminShell } from './components/layout/AppShell';
import { DashboardPage } from './pages/tenant/DashboardPage';
import { ModelCatalogPage } from './pages/tenant/discover/ModelCatalogPage';
import { ToolCatalogPage } from './pages/tenant/discover/ToolCatalogPage';
import { AgentListPage } from './pages/tenant/agents/AgentListPage';
import { AgentCreatePage } from './pages/tenant/agents/AgentCreatePage';
import { AgentTestBench } from './pages/tenant/agents/AgentTestBench';
import { AdminDashboard } from './pages/admin/AdminDashboard';
import { ServiceHealthPage } from './pages/admin/health/ServiceHealthPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Navigate to="/app" replace />} />

          {/* Tenant routes */}
          <Route path="/app" element={<TenantShell />}>
            <Route index element={<DashboardPage />} />
            <Route path="discover/models" element={<ModelCatalogPage />} />
            <Route path="discover/tools" element={<ToolCatalogPage />} />
            <Route path="agents" element={<AgentListPage />} />
            <Route path="agents/new" element={<AgentCreatePage />} />
            <Route path="agents/:name" element={<AgentTestBench />} />
            <Route path="agents/:name/test" element={<AgentTestBench />} />
          </Route>

          {/* Admin routes */}
          <Route path="/admin" element={<AdminShell />}>
            <Route index element={<AdminDashboard />} />
            <Route path="health" element={<ServiceHealthPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
