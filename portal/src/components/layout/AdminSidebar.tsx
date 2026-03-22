import { NavLink } from 'react-router-dom';
import { cn } from '../../lib/utils';

const navItems = [
  { label: 'Dashboard', path: '/admin', icon: '📊' },
  { label: 'Tenants', path: '/admin/tenants', icon: '🏢' },
  { label: 'Usage Analytics', path: '/admin/usage', icon: '📈' },
  { label: 'Memory', path: '/admin/memory', icon: '💾' },
  { label: 'Governance', path: '/admin/governance', icon: '🛡️' },
  { label: 'Service Health', path: '/admin/health', icon: '💚' },
];

export function AdminSidebar() {
  return (
    <aside className="w-56 bg-slate-900 text-gray-300 flex flex-col min-h-screen">
      <div className="p-4 border-b border-slate-700">
        <h1 className="text-lg font-bold text-white tracking-tight">NGEN Admin</h1>
        <p className="text-xs text-orange-400 mt-0.5">Platform Operations</p>
      </div>
      <nav className="flex-1 py-2 overflow-y-auto">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === '/admin'}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-2.5 px-4 py-2 text-sm transition-colors',
                isActive
                  ? 'bg-slate-800 text-white border-r-2 border-orange-500'
                  : 'hover:bg-slate-800/50 hover:text-white'
              )
            }
          >
            <span className="text-base">{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="p-3 border-t border-slate-700">
        <NavLink to="/app" className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-300 transition-colors">
          <span>◀</span> Back to Tenant View
        </NavLink>
      </div>
    </aside>
  );
}
