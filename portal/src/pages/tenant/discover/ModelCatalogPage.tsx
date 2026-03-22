import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../../../lib/constants';
import { formatCost, formatTokens } from '../../../lib/utils';
import { modelRegistryApi } from '../../../api/modelRegistryApi';
import { StatusBadge } from '../../../components/shared/StatusBadge';

export function ModelCatalogPage() {
  const [filter, setFilter] = useState('');

  const { data: models, isLoading } = useQuery({
    queryKey: queryKeys.models.all,
    queryFn: () => modelRegistryApi.list(),
  });

  const filtered = models?.filter((m) =>
    !filter || m.name.toLowerCase().includes(filter.toLowerCase()) || m.provider.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Model Catalog</h1>
        <p className="text-sm text-gray-500 mt-1">Browse available AI models provided by the platform</p>
      </div>

      <div className="mb-4">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Search models by name or provider..."
          className="w-80 px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>
      ) : !filtered || filtered.length === 0 ? (
        <div className="text-center py-20 bg-white rounded-xl border border-gray-200">
          <span className="text-4xl">🤖</span>
          <h3 className="mt-3 text-lg font-medium text-gray-900">
            {filter ? 'No models match your search' : 'No models available yet'}
          </h3>
          <p className="mt-1 text-sm text-gray-500">
            {filter ? 'Try a different search term' : 'Models are registered by the platform team and will appear here once available'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((model) => (
            <div key={model.id} className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm hover:shadow-md transition-shadow">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold text-gray-900">{model.name}</h3>
                <StatusBadge value={model.provider} />
              </div>
              <div className="flex gap-1 flex-wrap mb-3">
                {model.capabilities.map((cap) => (
                  <span key={cap} className="text-[10px] bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded">{cap}</span>
                ))}
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs text-gray-500 mb-3">
                <div>Context: {formatTokens(model.context_window)}</div>
                <div>Max output: {formatTokens(model.max_output_tokens)}</div>
                <div>Input: {formatCost(model.cost_per_m_input)}/M</div>
                <div>Output: {formatCost(model.cost_per_m_output)}/M</div>
              </div>
              <StatusBadge value={model.is_active ? 'active' : 'offline'} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
