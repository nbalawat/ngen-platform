import { NavLink } from 'react-router-dom';
import { cn } from '../../lib/utils';

const navItems = [
  { label: 'Dashboard', path: '/app', icon: '🏠' },
  { section: 'Build' },
  { label: 'Agents', path: '/app/agents', icon: '🧠' },
  { label: 'Workflows', path: '/app/workflows', icon: '⚡' },
  { label: 'Knowledge Base', path: '/app/knowledge', icon: '📚' },
  { section: 'Discover' },
  { label: 'Model Catalog', path: '/app/discover/models', icon: '🤖' },
  { label: 'Tool Catalog', path: '/app/discover/tools', icon: '🔧' },
  { section: 'Observe' },
  { label: 'Memory', path: '/app/memory', icon: '💾' },
  { label: 'Usage', path: '/app/usage', icon: '📊' },
];

export function TenantSidebar() {
  return (
    <aside className="w-56 bg-gray-900 text-gray-300 flex flex-col min-h-screen">
      <div className="p-4 border-b border-gray-700">
        <h1 className="text-lg font-bold text-white tracking-tight">NGEN Platform</h1>
        <p className="text-xs text-gray-500 mt-0.5">Tenant Workspace</p>
      </div>
      <nav className="flex-1 py-2 overflow-y-auto">
        {navItems.map((item) => {
          if ('section' in item) {
            return (
              <div key={item.section} className="px-4 pt-4 pb-1">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                  {item.section}
                </p>
              </div>
            );
          }
          return (
            <NavLink
              key={item.path}
              to={item.path!}
              end={item.path === '/app'}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2.5 px-4 py-2 text-sm transition-colors',
                  isActive
                    ? 'bg-gray-800 text-white border-r-2 border-blue-500'
                    : 'hover:bg-gray-800/50 hover:text-white'
                )
              }
            >
              <span className="text-base">{item.icon}</span>
              {item.label}
            </NavLink>
          );
        })}
      </nav>
      <div className="p-3 border-t border-gray-700">
        <NavLink to="/admin" className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-300 transition-colors">
          <span>🔑</span> Admin Console
        </NavLink>
      </div>
    </aside>
  );
}
