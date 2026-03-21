import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { apiFetch } from '../../../api/client';
import { API } from '../../../lib/constants';
import { StatusBadge } from '../../../components/shared/StatusBadge';

interface SSEEvent {
  event: string;
  data: Record<string, unknown> | null;
  timestamp: number;
}

export function WorkflowRunPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { yaml, inputData } = (location.state || {}) as { yaml?: string; inputData?: Record<string, unknown> };

  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [status, setStatus] = useState<string>('connecting');
  const [runId, setRunId] = useState<string>('');
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string>('');
  const [waitingApproval, setWaitingApproval] = useState(false);
  const [approving, setApproving] = useState(false);
  const eventsEndRef = useRef<HTMLDivElement>(null);
  const startTimeRef = useRef(Date.now());

  useEffect(() => {
    if (!yaml) {
      navigate('/app/workflows/new');
      return;
    }

    startTimeRef.current = Date.now();
    setStatus('running');

    // Use fetch for SSE streaming
    const controller = new AbortController();

    (async () => {
      try {
        const resp = await fetch(`${API.workflow}/workflows/run/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ workflow_yaml: yaml, input_data: inputData || {} }),
          signal: controller.signal,
        });

        if (!resp.ok) {
          const text = await resp.text();
          setError(`HTTP ${resp.status}: ${text}`);
          setStatus('failed');
          return;
        }

        const reader = resp.body?.getReader();
        if (!reader) { setError('No response body'); setStatus('failed'); return; }

        const decoder = new TextDecoder();
        let buffer = '';
        let currentEvent = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed) continue;

            // SSE comment (keepalive)
            if (trimmed.startsWith(':')) {
              setEvents((prev) => [...prev, { event: 'keepalive', data: null, timestamp: Date.now() }]);
              continue;
            }

            if (trimmed.startsWith('event: ')) {
              currentEvent = trimmed.slice(7);
              continue;
            }

            if (trimmed.startsWith('data: ')) {
              try {
                const data = JSON.parse(trimmed.slice(6));
                const evt: SSEEvent = {
                  event: currentEvent || 'message',
                  data,
                  timestamp: Date.now(),
                };
                setEvents((prev) => [...prev, evt]);

                // Handle terminal events
                if (currentEvent === 'done') {
                  setStatus('completed');
                  setRunId(data.run_id || '');
                  setResult(data.result || null);
                } else if (currentEvent === 'error') {
                  setStatus('failed');
                  setError(data.error || 'Unknown error');
                } else if (currentEvent === 'waiting_approval') {
                  setStatus('waiting_approval');
                  setWaitingApproval(true);
                  setRunId(data.run_id || '');
                }

                currentEvent = '';
              } catch { /* ignore parse errors */ }
            }
          }
        }

        // Stream ended without done/error event
        if (status === 'running') setStatus('completed');
      } catch (e: any) {
        if (e.name !== 'AbortError') {
          setError(e.message);
          setStatus('failed');
        }
      }
    })();

    return () => controller.abort();
  }, [yaml]);

  // Auto-scroll to bottom
  useEffect(() => {
    eventsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  const handleApprove = async () => {
    if (!runId) return;
    setApproving(true);
    try {
      await apiFetch(`${API.workflow}/workflows/runs/${runId}/approve`, { method: 'POST' });
      setWaitingApproval(false);
      setStatus('running');
    } catch (e: any) {
      setError(`Approval failed: ${e.message}`);
    } finally {
      setApproving(false);
    }
  };

  const handleCancel = async () => {
    if (!runId) return;
    try {
      await apiFetch(`${API.workflow}/workflows/runs/${runId}`, { method: 'DELETE' });
      setStatus('cancelled');
    } catch { /* ignore */ }
  };

  const elapsed = ((Date.now() - startTimeRef.current) / 1000).toFixed(1);
  const agentEvents = events.filter((e) => e.event !== 'keepalive' && e.event !== 'done' && e.event !== 'error');
  const agentNames = [...new Set(agentEvents.map((e) => e.data?.agent_name).filter(Boolean))] as string[];

  const getEventColor = (evt: string) => {
    switch (evt) {
      case 'thinking': return 'bg-purple-100 text-purple-700';
      case 'text_delta': return 'bg-blue-100 text-blue-700';
      case 'tool_call_start': return 'bg-amber-100 text-amber-700';
      case 'tool_call_end': return 'bg-amber-50 text-amber-600';
      case 'done': return 'bg-green-100 text-green-700';
      case 'error': return 'bg-red-100 text-red-700';
      case 'waiting_approval': return 'bg-yellow-100 text-yellow-800';
      case 'escalation': return 'bg-orange-100 text-orange-700';
      case 'keepalive': return 'bg-gray-100 text-gray-400';
      default: return 'bg-gray-100 text-gray-600';
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Workflow Execution</h1>
          <p className="text-sm text-gray-500 mt-1">
            {status === 'running' && '⏳ Streaming events in real-time...'}
            {status === 'completed' && '✅ Workflow completed successfully'}
            {status === 'failed' && '❌ Workflow failed'}
            {status === 'waiting_approval' && '⏸️ Waiting for human approval'}
            {status === 'cancelled' && '🚫 Workflow cancelled'}
            {status === 'connecting' && '🔄 Connecting...'}
          </p>
        </div>
        <div className="flex gap-2">
          {(status === 'running' || status === 'waiting_approval') && runId && (
            <button onClick={handleCancel} className="px-4 py-2 bg-red-100 text-red-700 rounded-lg text-sm font-medium hover:bg-red-200">
              Cancel Run
            </button>
          )}
          <button onClick={() => navigate('/app/workflows')} className="px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50">
            ← Back to Workflows
          </button>
        </div>
      </div>

      {/* Status Header */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm mb-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <StatusBadge value={status} />
            {runId && <span className="text-xs font-mono text-gray-500">Run: {runId.slice(0, 12)}...</span>}
            <span className="text-xs text-gray-400">{elapsed}s elapsed</span>
          </div>
          <div className="flex items-center gap-4 text-sm text-gray-500">
            <span>{events.filter((e) => e.event !== 'keepalive').length} events</span>
            <span>{agentNames.length} agents</span>
          </div>
        </div>

        {/* HITL Approval Banner */}
        {waitingApproval && (
          <div className="mt-4 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="font-medium text-yellow-800">⏸️ Human Approval Required</h4>
                <p className="text-sm text-yellow-700 mt-1">
                  The workflow has paused at an approval gate. Review the events below and approve to continue.
                </p>
              </div>
              <button
                onClick={handleApprove}
                disabled={approving}
                className="px-6 py-2.5 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-50 shadow-sm"
              >
                {approving ? 'Approving...' : '✓ Approve & Continue'}
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Event Timeline */}
        <div className="col-span-2">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
            <div className="px-5 py-3 border-b border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900">Event Stream</h3>
            </div>
            <div className="max-h-[600px] overflow-auto p-3 space-y-1.5">
              {events.length === 0 && status === 'running' && (
                <div className="text-center py-10 text-gray-400">
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600 mx-auto mb-3" />
                  <p className="text-sm">Waiting for events...</p>
                </div>
              )}
              {events.filter((e) => e.event !== 'keepalive').map((evt, i) => (
                <div key={i} className="flex items-start gap-2 text-sm">
                  <span className="text-xs text-gray-300 w-8 text-right pt-1 font-mono">{i + 1}</span>
                  <span className={`px-2 py-0.5 rounded text-xs font-medium whitespace-nowrap ${getEventColor(evt.event)}`}>
                    {evt.event}
                  </span>
                  {evt.data?.agent_name && (
                    <span className="px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded text-xs">{evt.data.agent_name as string}</span>
                  )}
                  <span className="text-gray-600 text-xs flex-1 truncate font-mono">
                    {evt.event === 'text_delta' && (evt.data?.data as any)?.text
                      ? String((evt.data?.data as any).text)
                      : evt.event === 'done'
                        ? `status=${evt.data?.status}`
                        : evt.event === 'waiting_approval'
                          ? `gate=${evt.data?.gate || ''}`
                          : JSON.stringify(evt.data).slice(0, 120)}
                  </span>
                </div>
              ))}
              <div ref={eventsEndRef} />
            </div>
          </div>
        </div>

        {/* Right Sidebar: Agents + Result */}
        <div className="space-y-5">
          {/* Agent Activity */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Agents</h3>
            {agentNames.length === 0 ? (
              <p className="text-xs text-gray-400">No agent activity yet</p>
            ) : (
              <div className="space-y-2">
                {agentNames.map((name) => {
                  const agentEvts = agentEvents.filter((e) => e.data?.agent_name === name);
                  const hasDone = agentEvts.some((e) => e.event === 'done');
                  const hasError = agentEvts.some((e) => e.event === 'error');
                  return (
                    <div key={name} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg">
                      <div className="flex items-center gap-2">
                        <span className={`w-2 h-2 rounded-full ${hasError ? 'bg-red-400' : hasDone ? 'bg-green-400' : 'bg-blue-400 animate-pulse'}`} />
                        <span className="text-sm font-medium text-gray-700">{name}</span>
                      </div>
                      <span className="text-xs text-gray-400">{agentEvts.length} events</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Result */}
          {result && (
            <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-900 mb-3">Result</h3>
              <pre className="bg-gray-50 p-3 rounded-lg text-xs font-mono overflow-auto max-h-60 whitespace-pre-wrap text-gray-700">
                {JSON.stringify(result, null, 2)}
              </pre>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="bg-red-50 rounded-xl border border-red-200 p-5">
              <h3 className="text-sm font-semibold text-red-800 mb-2">Error</h3>
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
