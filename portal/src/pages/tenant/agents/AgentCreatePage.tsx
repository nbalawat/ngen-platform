import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys, API } from '../../../lib/constants';
import { agentApi } from '../../../api/agentApi';
import { apiFetch } from '../../../api/client';

const FRAMEWORKS = [
  { value: 'default', label: 'Default (In-Memory)', desc: 'Built-in adapter for testing and prototyping' },
  { value: 'langgraph', label: 'LangGraph', desc: 'LangChain agent graphs with tool use and memory' },
  { value: 'claude-agent-sdk', label: 'Claude Agent SDK', desc: 'Anthropic native agent framework' },
  { value: 'crewai', label: 'CrewAI', desc: 'Multi-agent orchestration framework' },
  { value: 'adk', label: 'Google ADK', desc: 'Google Agent Development Kit' },
  { value: 'ms-agent-framework', label: 'Microsoft Agent', desc: 'Azure AI Agent Service' },
];

const PROMPT_TEMPLATES = [
  { label: 'Customer Support', prompt: 'You are a customer support agent for an enterprise SaaS platform. You help users resolve issues with their accounts, billing, and product features. Be empathetic, professional, and solution-oriented. Always ask clarifying questions before providing solutions. If you cannot resolve an issue, escalate to a human agent.' },
  { label: 'Code Review', prompt: 'You are a senior software engineer conducting code reviews. Analyze code for correctness, performance, security vulnerabilities, and adherence to best practices. Provide specific, actionable feedback with code examples. Prioritize critical issues over style preferences.' },
  { label: 'Research Analyst', prompt: 'You are a research analyst. When given a topic, you provide comprehensive analysis with supporting evidence. Structure your responses with clear sections: Summary, Key Findings, Analysis, and Recommendations. Cite sources when possible and acknowledge uncertainty.' },
  { label: 'Data Extractor', prompt: 'You are a data extraction agent. Parse unstructured text, documents, and messages to extract structured information. Output results as clean JSON. Handle edge cases gracefully and flag ambiguous fields.' },
  { label: 'Blank', prompt: '' },
];

interface ModelConfig {
  id: string;
  name: string;
  provider: string;
  is_active: boolean;
}

interface MCPServer {
  id: string;
  name: string;
  namespace: string;
  tools: Array<{ name: string; description: string }>;
}

export function AgentCreatePage() {
  const nav = useNavigate();
  const qc = useQueryClient();

  const [form, setForm] = useState({
    name: '',
    description: '',
    framework: 'default',
    model: 'default',
    system_prompt: PROMPT_TEMPLATES[0].prompt,
    namespace: 'default',
    metadata: {} as Record<string, unknown>,
  });
  const [selectedTools, setSelectedTools] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<'prompt' | 'config' | 'tools'>('prompt');
  const [error, setError] = useState('');
  const [promptCharCount, setPromptCharCount] = useState(PROMPT_TEMPLATES[0].prompt.length);

  // Fetch available models from registry
  const { data: models } = useQuery({
    queryKey: queryKeys.models.all,
    queryFn: () => apiFetch<ModelConfig[]>(`${API.registry}/api/v1/models`),
  });

  // Fetch available MCP servers/tools
  const { data: servers } = useQuery({
    queryKey: queryKeys.servers.all,
    queryFn: () => apiFetch<MCPServer[]>(`${API.mcp}/api/v1/servers`),
  });

  const createMut = useMutation({
    mutationFn: () => {
      const payload = {
        ...form,
        metadata: {
          ...form.metadata,
          namespace: form.namespace,
          tools: selectedTools.length > 0 ? selectedTools : undefined,
        },
      };
      return agentApi.create(payload);
    },
    onSuccess: (agent) => {
      qc.invalidateQueries({ queryKey: queryKeys.agents.all });
      nav(`/app/agents/${agent.name}/test`);
    },
    onError: (err: Error) => setError(err.message),
  });

  const updatePrompt = (prompt: string) => {
    setForm({ ...form, system_prompt: prompt });
    setPromptCharCount(prompt.length);
  };

  const allTools = (servers || []).flatMap((s) =>
    s.tools.map((t) => ({ server: s.name, tool: t.name, desc: t.description, key: `${s.name}/${t.name}` }))
  );

  const toggleTool = (key: string) => {
    setSelectedTools((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Create Agent</h1>
          <p className="text-sm text-gray-500 mt-1">Design and configure a new AI agent with custom prompts, models, and tools</p>
        </div>
        <button onClick={() => nav('/app/agents')} className="px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50">
          Cancel
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">{error}</div>
      )}

      <div className="grid grid-cols-3 gap-6">
        {/* Left: Main form */}
        <div className="col-span-2 space-y-5">
          {/* Identity */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Agent Identity</h3>
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Agent Name *</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '') })}
                  placeholder="customer-support-bot"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                />
                <p className="text-xs text-gray-400 mt-1">Lowercase letters, numbers, and hyphens</p>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Namespace</label>
                <input
                  type="text"
                  value={form.namespace}
                  onChange={(e) => setForm({ ...form, namespace: e.target.value })}
                  placeholder="default"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Description</label>
              <input
                type="text"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="Handles customer inquiries and support tickets"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
              />
            </div>
          </div>

          {/* Tabs */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
            <div className="flex border-b border-gray-200">
              {(['prompt', 'config', 'tools'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-5 py-3 text-sm font-medium border-b-2 transition-colors ${
                    activeTab === tab
                      ? 'border-blue-500 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                >
                  {tab === 'prompt' ? '📝 System Prompt' : tab === 'config' ? '⚙️ Configuration' : '🔧 Tools'}
                </button>
              ))}
            </div>

            <div className="p-5">
              {/* Prompt Tab */}
              {activeTab === 'prompt' && (
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <label className="text-sm font-medium text-gray-700">System Prompt</label>
                    <span className="text-xs text-gray-400">{promptCharCount} chars</span>
                  </div>

                  {/* Prompt Templates */}
                  <div className="flex gap-2 mb-3 flex-wrap">
                    {PROMPT_TEMPLATES.map((t) => (
                      <button
                        key={t.label}
                        onClick={() => updatePrompt(t.prompt)}
                        className="px-3 py-1 text-xs border border-gray-200 rounded-full hover:border-blue-400 hover:bg-blue-50 transition-colors"
                      >
                        {t.label}
                      </button>
                    ))}
                  </div>

                  <textarea
                    value={form.system_prompt}
                    onChange={(e) => updatePrompt(e.target.value)}
                    rows={12}
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none resize-y font-mono leading-relaxed"
                    placeholder="You are a helpful AI assistant..."
                  />
                  <p className="text-xs text-gray-400 mt-2">
                    Define the agent's personality, capabilities, constraints, and response format. Be specific about what the agent should and should not do.
                  </p>
                </div>
              )}

              {/* Config Tab */}
              {activeTab === 'config' && (
                <div className="space-y-5">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">Framework</label>
                    <div className="grid grid-cols-2 gap-3">
                      {FRAMEWORKS.map((fw) => (
                        <button
                          key={fw.value}
                          onClick={() => setForm({ ...form, framework: fw.value })}
                          className={`text-left p-3 border-2 rounded-lg transition-all ${
                            form.framework === fw.value
                              ? 'border-blue-500 bg-blue-50'
                              : 'border-gray-200 hover:border-gray-300'
                          }`}
                        >
                          <span className="text-sm font-medium text-gray-900">{fw.label}</span>
                          <p className="text-xs text-gray-500 mt-0.5">{fw.desc}</p>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">Model</label>
                    {models && models.length > 0 ? (
                      <div className="grid grid-cols-2 gap-3">
                        <button
                          onClick={() => setForm({ ...form, model: 'default' })}
                          className={`text-left p-3 border-2 rounded-lg transition-all ${
                            form.model === 'default' ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300'
                          }`}
                        >
                          <span className="text-sm font-medium">default</span>
                          <p className="text-xs text-gray-500">Platform default model</p>
                        </button>
                        {models.filter((m) => m.is_active).map((m) => (
                          <button
                            key={m.id}
                            onClick={() => setForm({ ...form, model: m.name })}
                            className={`text-left p-3 border-2 rounded-lg transition-all ${
                              form.model === m.name ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300'
                            }`}
                          >
                            <span className="text-sm font-medium">{m.name}</span>
                            <p className="text-xs text-gray-500">{m.provider}</p>
                          </button>
                        ))}
                      </div>
                    ) : (
                      <input
                        type="text"
                        value={form.model}
                        onChange={(e) => setForm({ ...form, model: e.target.value })}
                        placeholder="default"
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                      />
                    )}
                  </div>
                </div>
              )}

              {/* Tools Tab */}
              {activeTab === 'tools' && (
                <div>
                  <p className="text-sm text-gray-500 mb-4">
                    Attach MCP tools to give your agent capabilities like searching documents, querying databases, or calling external APIs.
                  </p>
                  {allTools.length > 0 ? (
                    <div className="space-y-2">
                      {allTools.map((t) => (
                        <label
                          key={t.key}
                          className={`flex items-start gap-3 p-3 border rounded-lg cursor-pointer transition-colors ${
                            selectedTools.includes(t.key)
                              ? 'border-blue-400 bg-blue-50'
                              : 'border-gray-200 hover:border-gray-300'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={selectedTools.includes(t.key)}
                            onChange={() => toggleTool(t.key)}
                            className="mt-0.5"
                          />
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-medium text-gray-900">{t.tool}</span>
                              <span className="text-xs text-gray-400">from {t.server}</span>
                            </div>
                            <p className="text-xs text-gray-500 mt-0.5">{t.desc}</p>
                          </div>
                        </label>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-8 bg-gray-50 rounded-lg">
                      <p className="text-sm text-gray-400">No MCP servers registered</p>
                      <p className="text-xs text-gray-400 mt-1">Register MCP servers to attach tools to your agent</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right: Summary + Actions */}
        <div className="space-y-5">
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm sticky top-5">
            <h3 className="text-sm font-semibold text-gray-900 mb-4">Agent Summary</h3>

            <div className="space-y-2.5 mb-5">
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Name</span>
                <span className="font-medium font-mono">{form.name || '—'}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Framework</span>
                <span className="font-medium">{form.framework}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Model</span>
                <span className="font-medium">{form.model}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Namespace</span>
                <span className="font-medium">{form.namespace}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Prompt Length</span>
                <span className="font-medium">{promptCharCount} chars</span>
              </div>
              {selectedTools.length > 0 && (
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Tools</span>
                  <span className="font-medium">{selectedTools.length} attached</span>
                </div>
              )}
            </div>

            {/* Prompt Preview */}
            {form.system_prompt && (
              <div className="mb-5">
                <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Prompt Preview</h4>
                <div className="bg-gray-50 p-3 rounded-lg text-xs text-gray-600 max-h-40 overflow-auto leading-relaxed">
                  {form.system_prompt.slice(0, 300)}{form.system_prompt.length > 300 ? '...' : ''}
                </div>
              </div>
            )}

            <button
              onClick={() => createMut.mutate()}
              disabled={!form.name || createMut.isPending}
              className="w-full px-4 py-2.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {createMut.isPending ? 'Creating...' : 'Create & Test Agent'}
            </button>

            {!form.name && (
              <p className="text-xs text-amber-600 mt-2 text-center">Enter an agent name to continue</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
