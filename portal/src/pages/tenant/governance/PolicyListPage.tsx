import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../../../lib/constants';
import { governanceApi } from '../../../api/governanceApi';
import { StatusBadge } from '../../../components/shared/StatusBadge';
import type { PolicyType, PolicyAction } from '../../../types/governance';

const POLICY_TYPES: PolicyType[] = ['content_filter', 'cost_limit', 'tool_restriction', 'rate_limit'];
const ACTIONS: PolicyAction[] = ['block', 'warn', 'log', 'escalate'];

export function PolicyListPage() {
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: '', policy_type: 'content_filter' as PolicyType, action: 'block' as PolicyAction, namespace: 'default', rules: '{}' });

  const { data: policies, isLoading } = useQuery({ queryKey: queryKeys.policies.all, queryFn: () => governanceApi.listPolicies() });

  const createMut = useMutation({
    mutationFn: () => governanceApi.createPolicy({ ...form, rules: JSON.parse(form.rules) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: queryKeys.policies.all }); setShowCreate(false); },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => governanceApi.deletePolicy(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.policies.all }),
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Governance Policies</h1>
          <p className="text-sm text-gray-500 mt-1">Manage content filters, cost limits, and tool restrictions</p>
        </div>
        <button onClick={() => setShowCreate(!showCreate)} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 shadow-sm">
          + Create Policy
        </button>
      </div>

      {showCreate && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm mb-6">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">Create Policy</h3>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Policy name" className="px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" />
            <input value={form.namespace} onChange={(e) => setForm({ ...form, namespace: e.target.value })} placeholder="Namespace" className="px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" />
            <select value={form.policy_type} onChange={(e) => setForm({ ...form, policy_type: e.target.value as PolicyType })} className="px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500">
              {POLICY_TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
            </select>
            <select value={form.action} onChange={(e) => setForm({ ...form, action: e.target.value as PolicyAction })} className="px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500">
              {ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          <label className="block text-xs font-medium text-gray-500 mb-1">Rules (JSON)</label>
          <textarea value={form.rules} onChange={(e) => setForm({ ...form, rules: e.target.value })} rows={3} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-xs font-mono outline-none focus:ring-2 focus:ring-blue-500 mb-3" />
          <button onClick={() => createMut.mutate()} disabled={!form.name} className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm disabled:opacity-50">Create</button>
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>
      ) : !policies || policies.length === 0 ? (
        <div className="text-center py-20 bg-white rounded-xl border border-gray-200">
          <span className="text-4xl">🛡️</span>
          <h3 className="mt-3 text-lg font-medium text-gray-900">No policies yet</h3>
          <p className="mt-1 text-sm text-gray-500">Create governance policies to enforce guardrails</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Action</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Namespace</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Enabled</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {policies.map((p) => (
                <tr key={p.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3"><span className="text-sm font-medium text-gray-900">{p.name}</span></td>
                  <td className="px-4 py-3"><StatusBadge value={p.policy_type.replace(/_/g, ' ')} /></td>
                  <td className="px-4 py-3"><StatusBadge value={p.action} /></td>
                  <td className="px-4 py-3 text-sm text-gray-500">{p.namespace}</td>
                  <td className="px-4 py-3"><span className={`text-xs ${p.enabled ? 'text-green-600' : 'text-gray-400'}`}>{p.enabled ? 'Yes' : 'No'}</span></td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => { if (confirm(`Delete "${p.name}"?`)) deleteMut.mutate(p.id); }} className="text-xs text-red-500 hover:text-red-700">Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
