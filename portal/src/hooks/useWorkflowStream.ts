import { useState, useRef, useCallback } from 'react';
import { API } from '../lib/constants';
import { getToken } from '../api/client';

export interface WorkflowEvent {
  type: string;
  data: Record<string, unknown>;
  agent_name?: string;
}

export type WorkflowStatus = 'idle' | 'connecting' | 'running' | 'waiting_approval' | 'completed' | 'failed' | 'cancelled';

const EVENT_COLORS: Record<string, string> = {
  thinking: 'text-purple-600',
  text_delta: 'text-blue-600',
  tool_call_start: 'text-amber-600',
  tool_call_end: 'text-amber-600',
  done: 'text-green-600',
  error: 'text-red-600',
};

export function getEventColor(type: string) {
  return EVENT_COLORS[type] || 'text-gray-500';
}

export function useWorkflowStream() {
  const [events, setEvents] = useState<WorkflowEvent[]>([]);
  const [status, setStatus] = useState<WorkflowStatus>('idle');
  const [result, setResult] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const startRef = useRef<number>(0);
  const [elapsed, setElapsed] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const start = useCallback(async (workflowYaml: string, inputData?: Record<string, unknown>) => {
    // Reset state
    setEvents([]);
    setStatus('connecting');
    setResult(null);
    setError(null);
    setRunId(null);
    setElapsed(0);
    startRef.current = Date.now();

    // Start elapsed timer
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      setElapsed(Math.round((Date.now() - startRef.current) / 100) / 10);
    }, 100);

    const abortController = new AbortController();
    abortRef.current = abortController;

    try {
      const token = getToken();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const resp = await fetch(`${API.workflow}/workflows/run/stream`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          workflow_yaml: workflowYaml,
          input_data: inputData || {},
        }),
        signal: abortController.signal,
      });

      if (!resp.ok || !resp.body) {
        setStatus('failed');
        setError(`HTTP ${resp.status}`);
        if (timerRef.current) clearInterval(timerRef.current);
        return;
      }

      setStatus('running');
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let currentEventType = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEventType = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            const dataStr = line.slice(6);
            try {
              const data = JSON.parse(dataStr);

              if (currentEventType === 'keepalive') continue;

              const event: WorkflowEvent = {
                type: currentEventType || data.type || 'unknown',
                data,
                agent_name: data.agent_name,
              };

              setEvents(prev => [...prev, event]);

              // Handle terminal events
              if (currentEventType === 'done' || data.type === 'done') {
                setStatus('completed');
                setRunId(data.run_id || null);
                setResult(data.result || data);
                if (timerRef.current) clearInterval(timerRef.current);
              } else if (currentEventType === 'error' || data.type === 'error') {
                setStatus('failed');
                setError(data.error || data.message || 'Unknown error');
                if (timerRef.current) clearInterval(timerRef.current);
              } else if (currentEventType === 'waiting_approval') {
                setStatus('waiting_approval');
                setRunId(data.run_id || null);
              }
            } catch {
              // Skip malformed JSON
            }
          }
        }
      }
    } catch (err: unknown) {
      if ((err as Error).name !== 'AbortError') {
        setStatus('failed');
        setError((err as Error).message);
      }
      if (timerRef.current) clearInterval(timerRef.current);
    }
  }, []);

  const cancel = useCallback(async () => {
    abortRef.current?.abort();
    if (runId) {
      const token = getToken();
      const headers: Record<string, string> = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;
      await fetch(`${API.workflow}/workflows/runs/${runId}`, {
        method: 'DELETE',
        headers,
      }).catch(() => {});
    }
    setStatus('cancelled');
    if (timerRef.current) clearInterval(timerRef.current);
  }, [runId]);

  const approve = useCallback(async () => {
    if (!runId) return;
    const token = getToken();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    await fetch(`${API.workflow}/workflows/runs/${runId}/approve`, {
      method: 'POST',
      headers,
    });
    setStatus('running');
  }, [runId]);

  const reset = useCallback(() => {
    setEvents([]);
    setStatus('idle');
    setResult(null);
    setError(null);
    setRunId(null);
    setElapsed(0);
    if (timerRef.current) clearInterval(timerRef.current);
  }, []);

  return { events, status, elapsed, runId, result, error, start, cancel, approve, reset };
}
