import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../../../lib/constants';
import { tenantApi } from '../../../api/tenantApi';
import { StatusBadge } from '../../../components/shared/StatusBadge';

export function OrgSettingsPage() {
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: '', slug: '', contact_email: '' });

  const { data: orgs, isLoading } = useQuery({ queryKey: queryKeys.orgs.all, queryFn: tenantApi.listOrgs });

  const createMut = useMutation({
    mutationFn: () => tenantApi.createOrg(form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: queryKeys.orgs.all }); setShowCreate(false); setForm({ name: '', slug: '', contact_email: '' }); },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => tenantApi.deleteOrg(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.orgs.all }),
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Organization Settings</h1>
          <p className="text-sm text-gray-500 mt-1">Manage organizations, teams, and projects</p>
        </div>
        <button onClick={() => setShowCreate(!showCreate)} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 shadow-sm">
          + Create Organization
        </button>
      </div>

      {showCreate && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm mb-6">
          <div className="grid grid-cols-3 gap-3 mb-3">
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Organization name" className="px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" />
            <input value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} placeholder="Slug (URL-friendly)" className="px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" />
            <input value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} placeholder="Contact email" className="px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
          <button onClick={() => createMut.mutate()} disabled={!form.name || !form.slug} className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm disabled:opacity-50">Create</button>
          {createMut.isError && <p className="mt-2 text-sm text-red-600">{(createMut.error as Error).message}</p>}
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Slug</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Tier</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {orgs?.map((org) => (
                <tr key={org.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">{org.name}</td>
                  <td className="px-4 py-3 text-sm text-gray-500 font-mono">{org.slug}</td>
                  <td className="px-4 py-3"><StatusBadge value={org.tier} /></td>
                  <td className="px-4 py-3"><StatusBadge value={org.status} /></td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => { if (confirm(`Delete "${org.name}"?`)) deleteMut.mutate(org.id); }} className="text-xs text-red-500 hover:text-red-700">Delete</button>
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
