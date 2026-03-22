import { useState, useRef, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys, API } from '../../../lib/constants';
import { formatRelative } from '../../../lib/utils';
import { agentApi } from '../../../api/agentApi';
import { apiFetch } from '../../../api/client';
import { StatusBadge } from '../../../components/shared/StatusBadge';

interface AgentEvent {
  type: string;
  data: Record<string, unknown>;
  agent_name: string;
}

function EventCard({ event }: { event: AgentEvent }) {
  const d = event.data as Record<string, string>;
  if (event.type === 'thinking') {
    return (
      <div className="flex items-start gap-2 bg-gray-50 rounded-lg px-3 py-2 my-1">
        <span className="text-sm mt-0.5">🧠</span>
        <p className="text-xs text-gray-500 italic">{d.text || 'Thinking...'}</p>
      </div>
    );
  }
  if (event.type === 'tool_call_start') {
    return (
      <div className="border border-amber-200 bg-amber-50 rounded-lg px-3 py-2 my-1">
        <div className="flex items-center gap-2">
          <span className="text-xs">🔧</span>
          <span className="text-xs font-semibold text-amber-800">Tool: {d.tool || 'unknown'}</span>
        </div>
        {'input' in event.data && (
          <p className="text-[10px] text-amber-600 mt-1 font-mono truncate">
            Input: {JSON.stringify(event.data.input)}
          </p>
        )}
      </div>
    );
  }
  if (event.type === 'tool_call_end') {
    return (
      <div className="border border-green-200 bg-green-50 rounded-lg px-3 py-2 my-1">
        <div className="flex items-center gap-2">
          <span className="text-xs">✅</span>
          <span className="text-xs font-semibold text-green-800">
            {d.tool || 'Tool'} — {d.status || 'done'}
          </span>
        </div>
        {d.output && (
          <p className="text-[10px] text-green-600 mt-1">{d.output}</p>
        )}
      </div>
    );
  }
  if (event.type === 'done' || event.type === 'text_delta') return null;
  return null;
}

export function AgentTestBench() {
  const { name } = useParams<{ name: string }>();
  const qc = useQueryClient();
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Array<{ role: string; content: string; events?: AgentEvent[] }>>([]);
  const [showPrompt, setShowPrompt] = useState(false);
  const messagesEnd = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: agent, isError: agentNotFound } = useQuery({
    queryKey: queryKeys.agents.detail(name!),
    queryFn: () => agentApi.get(name!),
    enabled: !!name,
    retry: false,
  });

  const { data: memory } = useQuery({
    queryKey: queryKeys.agents.memory(name!),
    queryFn: () => agentApi.getMemory(name!),
    enabled: !!name,
    refetchInterval: 5000,
  });

  const invokeMut = useMutation({
    mutationFn: (message: string) => agentApi.invoke(name!, {
      messages: [{ role: 'user', content: message }],
    }),
    onSuccess: (resp) => {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: resp.output || '(no output)', events: resp.events as AgentEvent[] },
      ]);
      qc.invalidateQueries({ queryKey: queryKeys.agents.detail(name!) });
      qc.invalidateQueries({ queryKey: queryKeys.agents.memory(name!) });
    },
    onError: (err: Error) => {
      setMessages((prev) => [
        ...prev,
        { role: 'error', content: err.message },
      ]);
    },
  });

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = () => {
    if (!input.trim() || invokeMut.isPending) return;
    const msg = input.trim();
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: msg }]);
    invokeMut.mutate(msg);
    inputRef.current?.focus();
  };

  const handleClear = async () => {
    setMessages([]);
    try {
      await apiFetch(`${API.workflow}/agents/${name}/memory`, { method: 'DELETE' });
      qc.invalidateQueries({ queryKey: queryKeys.agents.memory(name!) });
    } catch {
      // silently fail — conversation is cleared locally
    }
  };

  // Agent not found — show helpful error instead of broken chat
  if (agentNotFound) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-7rem)]">
        <div className="text-center max-w-md">
          <span className="text-5xl block mb-4">🔍</span>
          <h2 className="text-xl font-bold text-gray-900 mb-2">Agent not found</h2>
          <p className="text-sm text-gray-500 mb-1">
            The agent <span className="font-mono font-semibold">"{name}"</span> doesn't exist.
          </p>
          <p className="text-xs text-gray-400 mb-6">
            It may have been deleted, or the server was restarted (agents are stored in memory).
          </p>
          <div className="flex items-center justify-center gap-3">
            <Link
              to="/app/agents/new"
              className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
            >
              Create New Agent
            </Link>
            <Link
              to="/app/agents"
              className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors"
            >
              View All Agents
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-6 h-[calc(100vh-7rem)]">
      {/* Chat area */}
      <div className="flex-1 flex flex-col bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {/* Header */}
        <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="text-xl">🧠</span>
              <div>
                <h2 className="text-sm font-semibold text-gray-900">{name}</h2>
                <p className="text-xs text-gray-500">
                  {agent?.description || agent?.framework || 'loading...'} &middot; {agent?.invocation_count ?? 0} invocations
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {agent && <StatusBadge value={agent.status} />}
              {messages.length > 0 && (
                <button
                  onClick={handleClear}
                  className="text-xs text-gray-400 hover:text-red-500 transition-colors px-2 py-1 rounded hover:bg-gray-100"
                >
                  Clear
                </button>
              )}
            </div>
          </div>

          {/* Expandable system prompt */}
          {agent?.system_prompt && (
            <div className="mt-2">
              <button
                onClick={() => setShowPrompt(!showPrompt)}
                className="text-[10px] text-gray-400 hover:text-gray-600 transition-colors"
              >
                {showPrompt ? 'Hide' : 'Show'} system prompt
              </button>
              {showPrompt && (
                <div className="mt-1 bg-gray-100 rounded px-3 py-2">
                  <p className="text-xs text-gray-600 font-mono whitespace-pre-wrap">{agent.system_prompt}</p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="text-center py-12 text-gray-400">
              <span className="text-3xl block mb-2">💬</span>
              <p className="text-sm">Send a message to test your agent</p>
              {agent?.system_prompt && (
                <p className="text-xs mt-2 text-gray-300 max-w-md mx-auto">
                  This agent is configured as: {agent.system_prompt.slice(0, 100)}{agent.system_prompt.length > 100 ? '...' : ''}
                </p>
              )}
            </div>
          )}
          {messages.map((msg, i) => (
            <div key={i}>
              <div className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[80%] rounded-xl px-4 py-2.5 ${
                  msg.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : msg.role === 'error'
                    ? 'bg-red-50 text-red-700 border border-red-200'
                    : 'bg-gray-100 text-gray-900'
                }`}>
                  <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                </div>
              </div>
              {/* Structured event cards for assistant messages */}
              {msg.role === 'assistant' && msg.events && msg.events.length > 0 && (
                <div className="ml-4 mt-1 max-w-[75%]">
                  {msg.events.map((event, j) => (
                    <EventCard key={j} event={event} />
                  ))}
                </div>
              )}
            </div>
          ))}
          {invokeMut.isPending && (
            <div className="flex justify-start">
              <div className="bg-gray-100 rounded-xl px-4 py-2.5">
                <div className="flex items-center gap-1.5">
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEnd} />
        </div>

        {/* Input */}
        <div className="px-4 py-3 border-t border-gray-200 bg-white">
          <div className="flex gap-2">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              placeholder="Type a message to test your agent..."
              className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
              autoFocus
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || invokeMut.isPending}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Send
            </button>
          </div>
        </div>
      </div>

      {/* Memory sidebar */}
      <div className="w-72 bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col">
        <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
          <h3 className="text-sm font-semibold text-gray-900">Agent Memory</h3>
          <p className="text-xs text-gray-500">{memory?.length ?? 0} entries</p>
        </div>
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {(!memory || memory.length === 0) ? (
            <p className="text-xs text-gray-400 text-center py-4">No memory entries yet</p>
          ) : (
            memory.map((entry) => (
              <div key={entry.id} className="border border-gray-100 rounded-lg p-2">
                <div className="flex items-center gap-1.5 mb-1">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                    entry.role === 'user' ? 'bg-blue-50 text-blue-700' : 'bg-green-50 text-green-700'
                  }`}>
                    {entry.role || 'system'}
                  </span>
                  <span className="text-[10px] text-gray-400">{formatRelative(entry.created_at)}</span>
                </div>
                <p className="text-xs text-gray-600 line-clamp-3">{entry.content}</p>
              </div>
            ))
          )}
        </div>
        <div className="px-3 py-2 border-t border-gray-100">
          <Link to={`/app/memory`} className="text-[10px] text-blue-500 hover:text-blue-700">
            View full memory dashboard
          </Link>
        </div>
      </div>
    </div>
  );
}
