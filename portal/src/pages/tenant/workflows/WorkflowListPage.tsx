import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { apiFetch } from '../../../api/client';
import { API, queryKeys } from '../../../lib/constants';
import { formatRelative } from '../../../lib/utils';
import { StatusBadge } from '../../../components/shared/StatusBadge';

interface WorkflowRun {
  run_id: string;
  status: string;
  result: Record<string, unknown> | null;
  events: unknown[];
  error: string | null;
  created_at: number;
  updated_at: number;
}

const SAMPLE_YAML = `apiVersion: ngen.io/v1
kind: Workflow
metadata:
  name: hello-workflow
spec:
  topology: sequential
  agents:
  - ref: greeter-agent
`;

export function WorkflowListPage() {
  const [showRun, setShowRun] = useState(false);
  const [yaml, setYaml] = useState(SAMPLE_YAML);
  const [inputData, setInputData] = useState('{"message": "Hello from NGEN!"}');

  const { data: runs, isLoading, refetch } = useQuery({
    queryKey: queryKeys.workflows.runs,
    queryFn: () => apiFetch<WorkflowRun[]>(`${API.workflow}/workflows/runs`),
  });

  const runMut = useMutation({
    mutationFn: () => apiFetch<WorkflowRun>(`${API.workflow}/workflows/run`, {
      method: 'POST',
      body: JSON.stringify({ workflow_yaml: yaml, input_data: JSON.parse(inputData) }),
    }),
    onSuccess: () => { refetch(); setShowRun(false); },
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Workflows</h1>
          <p className="text-sm text-gray-500 mt-1">Run and monitor multi-agent workflow executions</p>
        </div>
        <button onClick={() => setShowRun(!showRun)} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors shadow-sm">
          + Run Workflow
        </button>
      </div>

      {showRun && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm mb-6">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">New Workflow Run</h3>
          <div className="grid grid-cols-2 gap-4 mb-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Workflow YAML</label>
              <textarea value={yaml} onChange={(e) => setYaml(e.target.value)} rows={10} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-xs font-mono outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Input Data (JSON)</label>
              <textarea value={inputData} onChange={(e) => setInputData(e.target.value)} rows={10} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-xs font-mono outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={() => runMut.mutate()} disabled={runMut.isPending} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
              {runMut.isPending ? 'Running...' : 'Run Workflow'}
            </button>
            <button onClick={() => setShowRun(false)} className="px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50">Cancel</button>
          </div>
          {runMut.isError && <p className="mt-2 text-sm text-red-600">{(runMut.error as Error).message}</p>}
          {runMut.data && (
            <div className="mt-3 p-3 bg-green-50 border border-green-200 rounded-lg">
              <p className="text-sm text-green-800">Workflow completed! Run ID: <code className="text-xs">{runMut.data.run_id}</code></p>
            </div>
          )}
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>
      ) : !runs || runs.length === 0 ? (
        <div className="text-center py-20 bg-white rounded-xl border border-gray-200">
          <span className="text-4xl">⚡</span>
          <h3 className="mt-3 text-lg font-medium text-gray-900">No workflow runs yet</h3>
          <p className="mt-1 text-sm text-gray-500">Run your first workflow to see results here</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Run ID</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Events</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Error</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {runs.map((run) => (
                <tr key={run.run_id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-sm font-mono text-gray-700">{run.run_id.slice(0, 8)}...</td>
                  <td className="px-4 py-3"><StatusBadge value={run.status} /></td>
                  <td className="px-4 py-3 text-sm text-gray-600">{run.events.length}</td>
                  <td className="px-4 py-3 text-sm text-gray-500">{formatRelative(run.created_at)}</td>
                  <td className="px-4 py-3 text-sm text-red-500">{run.error || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
