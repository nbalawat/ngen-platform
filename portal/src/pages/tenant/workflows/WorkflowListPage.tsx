import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { apiFetch } from '../../../api/client';
import { API, queryKeys } from '../../../lib/constants';
import { formatRelative } from '../../../lib/utils';
import { StatusBadge } from '../../../components/shared/StatusBadge';

interface WorkflowRun {
  run_id: string;
  status: string;
  result: Record<string, unknown> | null;
  events: Array<{ type: string; data: Record<string, unknown>; agent_name?: string }>;
  error: string | null;
  created_at: number;
  updated_at: number;
}

export function WorkflowListPage() {
  const navigate = useNavigate();
  const [expandedRun, setExpandedRun] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('');

  const { data: runs, isLoading, refetch } = useQuery({
    queryKey: queryKeys.workflows.runs,
    queryFn: () => apiFetch<WorkflowRun[]>(`${API.workflow}/workflows/runs`),
    refetchInterval: 5000,
  });

  const approveMut = useMutation({
    mutationFn: (runId: string) => apiFetch(`${API.workflow}/workflows/runs/${runId}/approve`, { method: 'POST' }),
    onSuccess: () => refetch(),
  });

  const cancelMut = useMutation({
    mutationFn: (runId: string) => apiFetch(`${API.workflow}/workflows/runs/${runId}`, { method: 'DELETE' }),
    onSuccess: () => refetch(),
  });

  const filteredRuns = statusFilter
    ? (runs || []).filter((r) => r.status === statusFilter)
    : (runs || []);

  const statusCounts = (runs || []).reduce((acc, r) => {
    acc[r.status] = (acc[r.status] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const getEventTypeColor = (type: string) => {
    switch (type) {
      case 'thinking': return 'text-purple-600';
      case 'text_delta': return 'text-blue-600';
      case 'tool_call_start': return 'text-amber-600';
      case 'done': return 'text-green-600';
      case 'error': return 'text-red-600';
      default: return 'text-gray-500';
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Workflows</h1>
          <p className="text-sm text-gray-500 mt-1">Run and monitor multi-agent workflow executions</p>
        </div>
        <button
          onClick={() => navigate('/app/workflows/new')}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors shadow-sm"
        >
          + New Workflow
        </button>
      </div>

      {/* Status filter chips */}
      {runs && runs.length > 0 && (
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setStatusFilter('')}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              !statusFilter ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            All ({runs.length})
          </button>
          {Object.entries(statusCounts).map(([s, c]) => (
            <button
              key={s}
              onClick={() => setStatusFilter(statusFilter === s ? '' : s)}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                statusFilter === s ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {s} ({c})
            </button>
          ))}
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>
      ) : filteredRuns.length === 0 ? (
        <div className="text-center py-20 bg-white rounded-xl border border-gray-200">
          <span className="text-4xl">⚡</span>
          <h3 className="mt-3 text-lg font-medium text-gray-900">
            {runs && runs.length > 0 ? 'No matching runs' : 'No workflow runs yet'}
          </h3>
          <p className="mt-1 text-sm text-gray-500">
            {runs && runs.length > 0 ? 'Try a different filter' : 'Create and run your first workflow'}
          </p>
          {(!runs || runs.length === 0) && (
            <button
              onClick={() => navigate('/app/workflows/new')}
              className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700"
            >
              Create Workflow
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {filteredRuns.map((run) => (
            <div key={run.run_id} className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              {/* Run header row */}
              <div
                className="px-5 py-3.5 flex items-center justify-between cursor-pointer hover:bg-gray-50 transition-colors"
                onClick={() => setExpandedRun(expandedRun === run.run_id ? null : run.run_id)}
              >
                <div className="flex items-center gap-4">
                  <span className="text-xs text-gray-400">{expandedRun === run.run_id ? '▼' : '▶'}</span>
                  <code className="text-sm font-mono text-gray-700">{run.run_id.slice(0, 12)}...</code>
                  <StatusBadge value={run.status} />
                </div>
                <div className="flex items-center gap-6 text-sm text-gray-500">
                  <span>{run.events.length} events</span>
                  <span>{formatRelative(run.created_at)}</span>
                  {run.error && <span className="text-red-500 text-xs">{run.error.slice(0, 40)}</span>}
                  {run.status === 'waiting_approval' && (
                    <button
                      onClick={(e) => { e.stopPropagation(); approveMut.mutate(run.run_id); }}
                      className="px-3 py-1 bg-green-600 text-white rounded text-xs font-medium hover:bg-green-700"
                    >
                      ✓ Approve
                    </button>
                  )}
                  {(run.status === 'running' || run.status === 'waiting_approval') && (
                    <button
                      onClick={(e) => { e.stopPropagation(); cancelMut.mutate(run.run_id); }}
                      className="px-3 py-1 bg-red-100 text-red-600 rounded text-xs font-medium hover:bg-red-200"
                    >
                      Cancel
                    </button>
                  )}
                </div>
              </div>

              {/* Expanded detail */}
              {expandedRun === run.run_id && (
                <div className="border-t border-gray-100 px-5 py-4">
                  <div className="grid grid-cols-2 gap-6">
                    {/* Event Timeline */}
                    <div>
                      <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Event Timeline</h4>
                      <div className="space-y-1 max-h-64 overflow-auto">
                        {run.events.map((evt, i) => (
                          <div key={i} className="flex items-start gap-2 text-xs">
                            <span className="text-gray-300 w-5 text-right font-mono">{i + 1}</span>
                            <span className={`font-medium ${getEventTypeColor(evt.type)}`}>{evt.type}</span>
                            {evt.agent_name && <span className="text-gray-400">[{evt.agent_name}]</span>}
                            <span className="text-gray-500 truncate flex-1 font-mono">
                              {evt.type === 'text_delta' && (evt.data as any)?.text
                                ? String((evt.data as any).text).slice(0, 80)
                                : JSON.stringify(evt.data).slice(0, 80)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Result */}
                    <div>
                      <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Result</h4>
                      {run.result ? (
                        <pre className="bg-gray-50 p-3 rounded-lg text-xs font-mono overflow-auto max-h-64 whitespace-pre-wrap text-gray-700">
                          {JSON.stringify(run.result, null, 2)}
                        </pre>
                      ) : (
                        <p className="text-xs text-gray-400">{run.error ? `Error: ${run.error}` : 'No result yet'}</p>
                      )}

                      {/* Run metadata */}
                      <div className="mt-3 space-y-1">
                        <div className="flex justify-between text-xs">
                          <span className="text-gray-500">Run ID</span>
                          <code className="text-gray-700">{run.run_id}</code>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-gray-500">Duration</span>
                          <span className="text-gray-700">{((run.updated_at - run.created_at) * 1000).toFixed(0)}ms</span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-gray-500">Agents</span>
                          <span className="text-gray-700">
                            {[...new Set(run.events.map((e) => e.agent_name).filter(Boolean))].join(', ') || '—'}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
