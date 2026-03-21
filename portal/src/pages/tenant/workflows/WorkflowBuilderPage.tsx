import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../../api/client';
import { API, queryKeys } from '../../../lib/constants';

interface AgentSummary {
  name: string;
  framework: string;
  status: string;
}

interface EdgeDef {
  from: string;
  to: string;
  condition: string;
}

const TOPOLOGIES = [
  { value: 'sequential', label: 'Sequential', icon: '➡️', desc: 'Agents execute one after another, each receiving previous outputs' },
  { value: 'parallel', label: 'Parallel', icon: '⚡', desc: 'All agents run concurrently, outputs merged at the end' },
  { value: 'graph', label: 'Graph (DAG)', icon: '🔀', desc: 'Directed acyclic graph with conditional edges between agents' },
  { value: 'hierarchical', label: 'Hierarchical', icon: '🏗️', desc: 'Supervisor-worker pattern: first agent delegates to workers' },
] as const;

const TEMPLATES = [
  {
    name: 'Research & Summarize',
    topology: 'sequential',
    agents: ['researcher', 'summarizer'],
    input: { query: 'Latest trends in AI agents' },
    desc: 'Sequential pipeline: research a topic then summarize findings',
  },
  {
    name: 'Parallel Analysis',
    topology: 'parallel',
    agents: ['sentiment-analyzer', 'topic-extractor', 'entity-detector'],
    input: { text: 'NGEN platform enables multi-agent AI orchestration at enterprise scale.' },
    desc: 'Run multiple analysis agents concurrently on the same input',
  },
  {
    name: 'Triage & Route',
    topology: 'hierarchical',
    agents: ['triage-agent', 'billing-agent', 'support-agent', 'escalation-agent'],
    input: { ticket: 'I was charged twice for my subscription' },
    desc: 'Supervisor triages the request, workers handle specific domains',
  },
  {
    name: 'Conditional Pipeline',
    topology: 'graph',
    agents: ['classifier', 'simple-handler', 'complex-handler', 'reviewer'],
    edges: [
      { from: 'classifier', to: 'simple-handler', condition: '' },
      { from: 'classifier', to: 'complex-handler', condition: '' },
      { from: 'simple-handler', to: 'reviewer', condition: '' },
      { from: 'complex-handler', to: 'reviewer', condition: '' },
    ],
    input: { request: 'Process this customer inquiry' },
    desc: 'DAG with conditional routing based on classification',
  },
];

function generateYaml(
  name: string,
  namespace: string,
  topology: string,
  agents: string[],
  edges: EdgeDef[],
  hitlGate: string,
  hitlTimeout: number,
): string {
  const lines: string[] = [
    'apiVersion: ngen.io/v1',
    'kind: Workflow',
    'metadata:',
    `  name: ${name || 'my-workflow'}`,
  ];
  if (namespace && namespace !== 'default') {
    lines.push(`  namespace: ${namespace}`);
  }
  lines.push('spec:');
  lines.push(`  topology: ${topology}`);
  lines.push('  agents:');
  for (const a of agents) {
    if (a.trim()) lines.push(`  - ref: ${a.trim()}`);
  }
  if (topology === 'graph' && edges.length > 0) {
    lines.push('  edges:');
    for (const e of edges) {
      lines.push(`  - from: ${e.from}`);
      lines.push(`    to: ${e.to}`);
      if (e.condition) lines.push(`    condition: "${e.condition}"`);
    }
  }
  if (hitlGate) {
    lines.push('  humanInTheLoop:');
    lines.push(`    approvalGate: ${hitlGate}`);
    lines.push(`    timeoutSeconds: ${hitlTimeout}`);
  }
  return lines.join('\n') + '\n';
}

export function WorkflowBuilderPage() {
  const navigate = useNavigate();
  const [name, setName] = useState('my-workflow');
  const [namespace, setNamespace] = useState('default');
  const [topology, setTopology] = useState('sequential');
  const [agents, setAgents] = useState<string[]>(['']);
  const [edges, setEdges] = useState<EdgeDef[]>([]);
  const [hitlGate, setHitlGate] = useState('');
  const [hitlTimeout, setHitlTimeout] = useState(3600);
  const [inputData, setInputData] = useState('{}');
  const [showYaml, setShowYaml] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState('');

  // Fetch available agents for the picker
  const { data: availableAgents } = useQuery({
    queryKey: queryKeys.agents.all,
    queryFn: () => apiFetch<AgentSummary[]>(`${API.workflow}/agents`),
  });

  const validAgents = agents.filter((a) => a.trim());
  const yaml = generateYaml(name, namespace, topology, validAgents, edges, hitlGate, hitlTimeout);

  const addAgent = () => setAgents([...agents, '']);
  const removeAgent = (i: number) => {
    const next = agents.filter((_, idx) => idx !== i);
    setAgents(next.length ? next : ['']);
  };
  const updateAgent = (i: number, val: string) => {
    const next = [...agents];
    next[i] = val;
    setAgents(next);
  };

  const addEdge = () => setEdges([...edges, { from: '', to: '', condition: '' }]);
  const removeEdge = (i: number) => setEdges(edges.filter((_, idx) => idx !== i));
  const updateEdge = (i: number, field: keyof EdgeDef, val: string) => {
    const next = [...edges];
    next[i] = { ...next[i], [field]: val };
    setEdges(next);
  };

  const applyTemplate = (t: typeof TEMPLATES[number]) => {
    setTopology(t.topology);
    setAgents(t.agents);
    setName(t.name.toLowerCase().replace(/\s+/g, '-'));
    setInputData(JSON.stringify(t.input, null, 2));
    if ('edges' in t && t.edges) setEdges(t.edges);
    else setEdges([]);
    setHitlGate('');
  };

  const handleRun = async (stream: boolean) => {
    setError('');
    setIsRunning(true);
    try {
      let parsedInput = {};
      try { parsedInput = JSON.parse(inputData); } catch { /* keep {} */ }

      if (stream) {
        // Navigate to streaming run page with state
        navigate('/app/workflows/run', {
          state: { yaml, inputData: parsedInput },
        });
        return;
      }

      const result = await apiFetch(`${API.workflow}/workflows/run`, {
        method: 'POST',
        body: JSON.stringify({ workflow_yaml: yaml, input_data: parsedInput }),
      });
      navigate('/app/workflows');
    } catch (e: any) {
      setError(e.message || 'Failed to run workflow');
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Workflow Builder</h1>
          <p className="text-sm text-gray-500 mt-1">Design, configure, and execute multi-agent workflows</p>
        </div>
        <button onClick={() => navigate('/app/workflows')} className="px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50">
          ← Back to Runs
        </button>
      </div>

      {/* Templates */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm mb-6">
        <h3 className="text-sm font-semibold text-gray-900 mb-3">Quick Start Templates</h3>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {TEMPLATES.map((t) => (
            <button
              key={t.name}
              onClick={() => applyTemplate(t)}
              className="text-left p-3 border border-gray-200 rounded-lg hover:border-blue-400 hover:bg-blue-50 transition-colors"
            >
              <div className="font-medium text-sm text-gray-900">{t.name}</div>
              <div className="text-xs text-gray-500 mt-1">{t.desc}</div>
              <div className="mt-2">
                <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs">{t.topology}</span>
                <span className="ml-1 text-xs text-gray-400">{t.agents.length} agents</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Left: Configuration */}
        <div className="col-span-2 space-y-5">
          {/* Basic Info */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Workflow Configuration</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Workflow Name</label>
                <input value={name} onChange={(e) => setName(e.target.value)} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" placeholder="my-workflow" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Namespace</label>
                <input value={namespace} onChange={(e) => setNamespace(e.target.value)} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" placeholder="default" />
              </div>
            </div>
          </div>

          {/* Topology Selection */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Topology</h3>
            <div className="grid grid-cols-2 gap-3">
              {TOPOLOGIES.map((t) => (
                <button
                  key={t.value}
                  onClick={() => {
                    setTopology(t.value);
                    if (t.value !== 'graph') setEdges([]);
                  }}
                  className={`text-left p-3 border-2 rounded-lg transition-all ${
                    topology === t.value
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{t.icon}</span>
                    <span className="font-medium text-sm text-gray-900">{t.label}</span>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">{t.desc}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Agent List */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-900">
                Agents
                {topology === 'hierarchical' && <span className="text-xs text-gray-400 font-normal ml-2">(first agent = supervisor)</span>}
              </h3>
              <button onClick={addAgent} className="text-xs text-blue-600 hover:text-blue-700 font-medium">+ Add Agent</button>
            </div>
            <div className="space-y-2">
              {agents.map((agent, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="text-xs text-gray-400 w-6 text-right">{i + 1}.</span>
                  {topology === 'hierarchical' && i === 0 && (
                    <span className="px-1.5 py-0.5 bg-amber-100 text-amber-700 rounded text-xs font-medium">Supervisor</span>
                  )}
                  {topology === 'hierarchical' && i > 0 && (
                    <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded text-xs font-medium">Worker</span>
                  )}
                  {availableAgents && availableAgents.length > 0 ? (
                    <select
                      value={agent}
                      onChange={(e) => updateAgent(i, e.target.value)}
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="">Select an agent...</option>
                      {availableAgents.map((a) => (
                        <option key={a.name} value={a.name}>{a.name} ({a.framework})</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      value={agent}
                      onChange={(e) => updateAgent(i, e.target.value)}
                      placeholder="agent-name"
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  )}
                  {agents.length > 1 && (
                    <button onClick={() => removeAgent(i)} className="text-red-400 hover:text-red-600 text-sm">✕</button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Edges (Graph topology) */}
          {topology === 'graph' && (
            <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-gray-900">Edges (Transitions)</h3>
                <button onClick={addEdge} className="text-xs text-blue-600 hover:text-blue-700 font-medium">+ Add Edge</button>
              </div>
              {edges.length === 0 ? (
                <p className="text-xs text-gray-400">No edges defined. Add edges to connect agents in the graph.</p>
              ) : (
                <div className="space-y-2">
                  {edges.map((edge, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <select value={edge.from} onChange={(e) => updateEdge(i, 'from', e.target.value)} className="flex-1 px-2 py-1.5 border border-gray-300 rounded text-sm">
                        <option value="">From...</option>
                        {validAgents.map((a) => <option key={a} value={a}>{a}</option>)}
                      </select>
                      <span className="text-gray-400">→</span>
                      <select value={edge.to} onChange={(e) => updateEdge(i, 'to', e.target.value)} className="flex-1 px-2 py-1.5 border border-gray-300 rounded text-sm">
                        <option value="">To...</option>
                        {validAgents.map((a) => <option key={a} value={a}>{a}</option>)}
                      </select>
                      <input
                        value={edge.condition}
                        onChange={(e) => updateEdge(i, 'condition', e.target.value)}
                        placeholder="condition (optional)"
                        className="flex-1 px-2 py-1.5 border border-gray-300 rounded text-xs font-mono"
                      />
                      <button onClick={() => removeEdge(i)} className="text-red-400 hover:text-red-600 text-sm">✕</button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* HITL Gate */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Human-in-the-Loop Approval</h3>
            <p className="text-xs text-gray-500 mb-3">Optionally pause the workflow after a specific agent completes and wait for human approval before continuing.</p>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Approval Gate (agent name)</label>
                <select value={hitlGate} onChange={(e) => setHitlGate(e.target.value)} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500">
                  <option value="">None (no approval gate)</option>
                  {validAgents.map((a) => <option key={a} value={a}>{a}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Timeout (seconds)</label>
                <input type="number" value={hitlTimeout} onChange={(e) => setHitlTimeout(Number(e.target.value))} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
            </div>
          </div>

          {/* Input Data */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Input Data (JSON)</h3>
            <textarea
              value={inputData}
              onChange={(e) => setInputData(e.target.value)}
              rows={4}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono outline-none focus:ring-2 focus:ring-blue-500"
              placeholder='{"query": "Hello from NGEN!"}'
            />
          </div>
        </div>

        {/* Right: YAML Preview + Actions */}
        <div className="space-y-5">
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm sticky top-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-900">Generated YAML</h3>
              <button onClick={() => setShowYaml(!showYaml)} className="text-xs text-blue-600 hover:text-blue-700">
                {showYaml ? 'Hide' : 'Show'}
              </button>
            </div>
            {showYaml && (
              <pre className="bg-gray-900 text-green-400 p-3 rounded-lg text-xs font-mono overflow-auto max-h-80 mb-4 whitespace-pre-wrap">{yaml}</pre>
            )}

            {/* Summary */}
            <div className="space-y-2 mb-4">
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Topology</span>
                <span className="font-medium">{topology}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Agents</span>
                <span className="font-medium">{validAgents.length}</span>
              </div>
              {topology === 'graph' && (
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Edges</span>
                  <span className="font-medium">{edges.length}</span>
                </div>
              )}
              {hitlGate && (
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Approval Gate</span>
                  <span className="font-medium text-amber-600">{hitlGate}</span>
                </div>
              )}
            </div>

            {error && <p className="text-sm text-red-600 mb-3">{error}</p>}

            <div className="space-y-2">
              <button
                onClick={() => handleRun(true)}
                disabled={isRunning || validAgents.length === 0}
                className="w-full px-4 py-2.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                ▶ Run with Live Stream
              </button>
              <button
                onClick={() => handleRun(false)}
                disabled={isRunning || validAgents.length === 0}
                className="w-full px-4 py-2 border border-gray-300 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50 disabled:opacity-50 transition-colors"
              >
                {isRunning ? 'Running...' : 'Run (Blocking)'}
              </button>
            </div>

            {validAgents.length === 0 && (
              <p className="text-xs text-amber-600 mt-2">Add at least one agent to run</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
