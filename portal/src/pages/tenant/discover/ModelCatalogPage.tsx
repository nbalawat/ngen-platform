import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../../../lib/constants';
import { formatCost, formatTokens } from '../../../lib/utils';
import { modelRegistryApi } from '../../../api/modelRegistryApi';
import { StatusBadge } from '../../../components/shared/StatusBadge';
import type { ModelProvider, ModelCapability } from '../../../types/model';

const PROVIDERS: ModelProvider[] = ['ANTHROPIC', 'OPENAI', 'GOOGLE', 'AZURE', 'LOCAL'];

export function ModelCatalogPage() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: '', provider: 'ANTHROPIC' as ModelProvider, endpoint: '', capabilities: [] as ModelCapability[] });

  const { data: models, isLoading } = useQuery({
    queryKey: queryKeys.models.all,
    queryFn: () => modelRegistryApi.list(),
  });

  const createMut = useMutation({
    mutationFn: () => modelRegistryApi.create(form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: queryKeys.models.all }); setShowCreate(false); },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => modelRegistryApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.models.all }),
  });

  const filtered = models?.filter((m) =>
    !filter || m.name.toLowerCase().includes(filter.toLowerCase()) || m.provider.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Model Catalog</h1>
          <p className="text-sm text-gray-500 mt-1">Browse and register AI models</p>
        </div>
        <button onClick={() => setShowCreate(!showCreate)} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors shadow-sm">
          + Register Model
        </button>
      </div>

      {showCreate && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm mb-6">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">Register New Model</h3>
          <div className="grid grid-cols-3 gap-3 mb-3">
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Model name" className="px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" />
            <select value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value as ModelProvider })} className="px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500">
              {PROVIDERS.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
            <input value={form.endpoint} onChange={(e) => setForm({ ...form, endpoint: e.target.value })} placeholder="Endpoint URL" className="px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
          <button onClick={() => createMut.mutate()} disabled={!form.name || !form.endpoint} className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm disabled:opacity-50">
            Register
          </button>
        </div>
      )}

      <div className="mb-4">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Search models..."
          className="w-64 px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered?.map((model) => (
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
              <div className="flex items-center justify-between">
                <StatusBadge value={model.is_active ? 'active' : 'offline'} />
                <button onClick={() => { if (confirm(`Delete "${model.name}"?`)) deleteMut.mutate(model.id); }} className="text-xs text-red-500 hover:text-red-700">Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
