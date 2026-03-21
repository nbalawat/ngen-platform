import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../../../lib/constants';
import { formatCost } from '../../../lib/utils';
import { governanceApi } from '../../../api/governanceApi';

export function BudgetDashboard() {
  const { data: budgets, isLoading } = useQuery({
    queryKey: queryKeys.budgets.all,
    queryFn: governanceApi.listBudgets,
    refetchInterval: 15000,
  });

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Budget Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">Monitor daily spend across namespaces</p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>
      ) : !budgets || budgets.length === 0 ? (
        <div className="text-center py-20 bg-white rounded-xl border border-gray-200">
          <span className="text-4xl">💰</span>
          <h3 className="mt-3 text-lg font-medium text-gray-900">No spend tracked yet</h3>
          <p className="mt-1 text-sm text-gray-500">Make requests through the model gateway to see budget data</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {(budgets as Array<Record<string, unknown>>).map((b, i) => (
            <div key={i} className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-900 mb-1">{String(b.namespace)}</h3>
              <p className="text-xs text-gray-400 mb-3">{String(b.date || 'No data')}</p>
              <div className="text-2xl font-bold text-gray-900 mb-2">{formatCost(Number(b.total_cost || 0))}</div>
              <div className="grid grid-cols-2 gap-2 text-xs text-gray-500">
                <div>Tokens: {String(b.total_tokens || 0)}</div>
                <div>Requests: {String(b.request_count || 0)}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
