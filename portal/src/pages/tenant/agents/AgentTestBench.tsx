import { useState, useRef, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../../../lib/constants';
import { formatRelative } from '../../../lib/utils';
import { agentApi } from '../../../api/agentApi';
import { StatusBadge } from '../../../components/shared/StatusBadge';

export function AgentTestBench() {
  const { name } = useParams<{ name: string }>();
  const qc = useQueryClient();
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Array<{ role: string; content: string; events?: unknown[] }>>([]);
  const messagesEnd = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: agent } = useQuery({
    queryKey: queryKeys.agents.detail(name!),
    queryFn: () => agentApi.get(name!),
    enabled: !!name,
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
        { role: 'assistant', content: resp.output || '(no output)', events: resp.events },
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

  return (
    <div className="flex gap-6 h-[calc(100vh-7rem)]">
      {/* Chat area */}
      <div className="flex-1 flex flex-col bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {/* Header */}
        <div className="px-4 py-3 border-b border-gray-200 bg-gray-50 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-xl">🧠</span>
            <div>
              <h2 className="text-sm font-semibold text-gray-900">{name}</h2>
              <p className="text-xs text-gray-500">{agent?.framework || 'loading...'} &middot; {agent?.invocation_count ?? 0} invocations</p>
            </div>
          </div>
          {agent && <StatusBadge value={agent.status} />}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="text-center py-12 text-gray-400">
              <span className="text-3xl block mb-2">💬</span>
              <p className="text-sm">Send a message to test your agent</p>
            </div>
          )}
          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[80%] rounded-xl px-4 py-2.5 ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : msg.role === 'error'
                  ? 'bg-red-50 text-red-700 border border-red-200'
                  : 'bg-gray-100 text-gray-900'
              }`}>
                <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                {msg.events && (
                  <details className="mt-2">
                    <summary className={`text-xs cursor-pointer ${msg.role === 'user' ? 'text-blue-200' : 'text-gray-400'}`}>
                      {(msg.events as unknown[]).length} events
                    </summary>
                    <div className="mt-1 text-xs space-y-0.5 opacity-70">
                      {(msg.events as Array<{ type: string; agent_name: string }>).map((e, j) => (
                        <div key={j} className="font-mono">{e.type} ({e.agent_name})</div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
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
      </div>
    </div>
  );
}
