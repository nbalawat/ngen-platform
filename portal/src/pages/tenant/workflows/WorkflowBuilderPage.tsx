import { useState, useRef, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
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

interface SavedWorkflow {
  name: string;
  version_count: number;
  latest_version: number;
  description: string;
  updated_at: number;
}

interface WorkflowVersionDetail {
  workflow_name: string;
  version: number;
  yaml_content: string;
  input_data: Record<string, unknown>;
  description: string;
  created_at: number;
}

const TOPOLOGIES = [
  { value: 'sequential', label: 'Sequential', icon: '➡️', desc: 'Agents execute one after another' },
  { value: 'parallel', label: 'Parallel', icon: '⚡', desc: 'All agents run concurrently' },
  { value: 'graph', label: 'Graph (DAG)', icon: '🔀', desc: 'Directed graph with conditional edges' },
  { value: 'hierarchical', label: 'Hierarchical', icon: '🏗️', desc: 'Supervisor delegates to workers' },
] as const;

const TEMPLATES = [
  { name: 'Research & Summarize', topology: 'sequential', agents: ['researcher', 'summarizer'], input: { query: 'Latest trends in AI agents' }, desc: 'Sequential pipeline' },
  { name: 'Parallel Analysis', topology: 'parallel', agents: ['sentiment-analyzer', 'topic-extractor', 'entity-detector'], input: { text: 'Analyze this text.' }, desc: 'Concurrent analysis' },
  { name: 'Triage & Route', topology: 'hierarchical', agents: ['triage-agent', 'billing-agent', 'support-agent'], input: { ticket: 'Billing issue' }, desc: 'Supervisor-worker' },
  { name: 'Conditional Pipeline', topology: 'graph', agents: ['classifier', 'simple-handler', 'complex-handler'], edges: [{ from: 'classifier', to: 'simple-handler', condition: '' }, { from: 'classifier', to: 'complex-handler', condition: '' }], input: { request: 'Process inquiry' }, desc: 'DAG routing' },
];

function generateYaml(name: string, namespace: string, topology: string, agents: string[], edges: EdgeDef[], hitlGate: string, hitlTimeout: number): string {
  const safeName = (name || 'my-workflow').replace(/[^a-z0-9-]+/g, '-').replace(/^-|-$/g, '') || 'my-workflow';
  const lines: string[] = ['apiVersion: ngen.io/v1', 'kind: Workflow', 'metadata:', `  name: ${safeName}`];
  if (namespace && namespace !== 'default') lines.push(`  namespace: ${namespace}`);
  lines.push('spec:', `  topology: ${topology}`, '  agents:');
  for (const a of agents) { if (a.trim()) lines.push(`  - ref: ${a.trim()}`); }
  if (topology === 'graph' && edges.length > 0) {
    lines.push('  edges:');
    for (const e of edges) {
      lines.push(`  - from: ${e.from}`, `    to: ${e.to}`);
      if (e.condition) lines.push(`    condition: "${e.condition}"`);
    }
  }
  if (hitlGate) { lines.push('  humanInTheLoop:', `    approvalGate: ${hitlGate}`, `    timeoutSeconds: ${hitlTimeout}`); }
  return lines.join('\n') + '\n';
}

// ---------------------------------------------------------------------------
// Visual Graph Canvas Component
// ---------------------------------------------------------------------------

function GraphCanvas({ agents, edges, onAddEdge, onRemoveEdge }: {
  agents: string[];
  edges: EdgeDef[];
  onAddEdge: (from: string, to: string) => void;
  onRemoveEdge: (i: number) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [dragFrom, setDragFrom] = useState<string | null>(null);

  const nodePositions = useCallback(() => {
    const positions: Record<string, { x: number; y: number }> = {};
    const count = agents.length;
    const w = 600, h = 320;
    const cx = w / 2, cy = h / 2;
    const radius = Math.min(w, h) * 0.35;
    agents.forEach((a, i) => {
      const angle = (2 * Math.PI * i) / count - Math.PI / 2;
      positions[a] = { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) };
    });
    return positions;
  }, [agents]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = 600 * dpr;
    canvas.height = 320 * dpr;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, 600, 320);

    const pos = nodePositions();

    // Draw edges
    edges.forEach((e, i) => {
      const from = pos[e.from];
      const to = pos[e.to];
      if (!from || !to) return;
      ctx.beginPath();
      ctx.moveTo(from.x, from.y);
      ctx.lineTo(to.x, to.y);
      ctx.strokeStyle = '#3b82f6';
      ctx.lineWidth = 2;
      ctx.stroke();

      // Arrowhead
      const angle = Math.atan2(to.y - from.y, to.x - from.x);
      const headLen = 12;
      const endX = to.x - 22 * Math.cos(angle);
      const endY = to.y - 22 * Math.sin(angle);
      ctx.beginPath();
      ctx.moveTo(endX, endY);
      ctx.lineTo(endX - headLen * Math.cos(angle - 0.4), endY - headLen * Math.sin(angle - 0.4));
      ctx.lineTo(endX - headLen * Math.cos(angle + 0.4), endY - headLen * Math.sin(angle + 0.4));
      ctx.closePath();
      ctx.fillStyle = '#3b82f6';
      ctx.fill();

      // Condition label
      if (e.condition) {
        const mx = (from.x + to.x) / 2;
        const my = (from.y + to.y) / 2;
        ctx.font = '10px monospace';
        ctx.fillStyle = '#6b7280';
        ctx.textAlign = 'center';
        ctx.fillText(e.condition.slice(0, 20), mx, my - 8);
      }
    });

    // Draw nodes
    Object.entries(pos).forEach(([name, p]) => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 20, 0, 2 * Math.PI);
      ctx.fillStyle = dragFrom === name ? '#2563eb' : '#dbeafe';
      ctx.fill();
      ctx.strokeStyle = '#3b82f6';
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.font = '12px sans-serif';
      ctx.fillStyle = '#1e3a5f';
      ctx.textAlign = 'center';
      ctx.fillText(name.length > 12 ? name.slice(0, 10) + '..' : name, p.x, p.y + 35);
    });
  }, [agents, edges, dragFrom, nodePositions]);

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const pos = nodePositions();

    const clicked = Object.entries(pos).find(([_, p]) => Math.hypot(p.x - x, p.y - y) < 25);
    if (!clicked) { setDragFrom(null); return; }

    if (dragFrom && dragFrom !== clicked[0]) {
      onAddEdge(dragFrom, clicked[0]);
      setDragFrom(null);
    } else {
      setDragFrom(clicked[0]);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs text-gray-500">
          {dragFrom ? `Click a target node to connect from "${dragFrom}"` : 'Click a node to start an edge, then click the target'}
        </p>
        {dragFrom && (
          <button onClick={() => setDragFrom(null)} className="text-xs text-red-500 hover:text-red-700">Cancel</button>
        )}
      </div>
      <canvas
        ref={canvasRef}
        width={600}
        height={320}
        className="border border-gray-200 rounded-lg cursor-crosshair bg-white"
        style={{ width: '100%', height: 320 }}
        onClick={handleCanvasClick}
      />
      {edges.length > 0 && (
        <div className="mt-2 space-y-1">
          {edges.map((e, i) => (
            <div key={i} className="flex items-center gap-2 text-xs bg-gray-50 px-2 py-1 rounded">
              <span className="font-medium text-blue-600">{e.from}</span>
              <span className="text-gray-400">→</span>
              <span className="font-medium text-blue-600">{e.to}</span>
              {e.condition && <span className="text-gray-400 font-mono">if: {e.condition}</span>}
              <button onClick={() => onRemoveEdge(i)} className="ml-auto text-red-400 hover:text-red-600">✕</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Main Builder Page
// ---------------------------------------------------------------------------

export function WorkflowBuilderPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
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
  const [saveDesc, setSaveDesc] = useState('');
  const [showSaved, setShowSaved] = useState(false);
  const [showVersions, setShowVersions] = useState(false);

  const { data: availableAgents } = useQuery({
    queryKey: queryKeys.agents.all,
    queryFn: () => apiFetch<AgentSummary[]>(`${API.workflow}/agents`),
  });

  const { data: savedWorkflows, refetch: refetchSaved } = useQuery({
    queryKey: ['versions', 'workflows'],
    queryFn: () => apiFetch<SavedWorkflow[]>(`${API.workflow}/versions/workflows`),
  });

  const validAgents = agents.filter((a) => a.trim());
  const yaml = generateYaml(name, namespace, topology, validAgents, edges, hitlGate, hitlTimeout);

  const addAgent = () => setAgents([...agents, '']);
  const removeAgent = (i: number) => { const n = agents.filter((_, idx) => idx !== i); setAgents(n.length ? n : ['']); };
  const updateAgent = (i: number, val: string) => { const n = [...agents]; n[i] = val; setAgents(n); };

  const addEdge = (from: string, to: string) => {
    if (!edges.some((e) => e.from === from && e.to === to)) {
      setEdges([...edges, { from, to, condition: '' }]);
    }
  };
  const removeEdge = (i: number) => setEdges(edges.filter((_, idx) => idx !== i));
  const updateEdgeCondition = (i: number, condition: string) => {
    const n = [...edges]; n[i] = { ...n[i], condition }; setEdges(n);
  };

  const applyTemplate = (t: typeof TEMPLATES[number]) => {
    setTopology(t.topology);
    setAgents(t.agents);
    setName(t.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''));
    setInputData(JSON.stringify(t.input, null, 2));
    if ('edges' in t && t.edges) setEdges(t.edges); else setEdges([]);
    setHitlGate('');
  };

  const saveMut = useMutation({
    mutationFn: () => {
      let parsedInput = {};
      try { parsedInput = JSON.parse(inputData); } catch { /* */ }
      return apiFetch(`${API.workflow}/versions/workflows`, {
        method: 'POST',
        body: JSON.stringify({ name, yaml_content: yaml, input_data: parsedInput, description: saveDesc }),
      });
    },
    onSuccess: () => { refetchSaved(); setSaveDesc(''); },
  });

  const loadVersion = async (wfName: string, version: number) => {
    const v = await apiFetch<WorkflowVersionDetail>(`${API.workflow}/versions/workflows/${wfName}/${version}`);
    // Parse YAML to extract topology, agents, etc.
    setName(v.workflow_name);
    setInputData(JSON.stringify(v.input_data, null, 2));
    // Try to parse the yaml_content for topology/agents
    try {
      const lines = v.yaml_content.split('\n');
      const topoLine = lines.find((l) => l.trim().startsWith('topology:'));
      if (topoLine) setTopology(topoLine.split(':')[1].trim());
      const agentRefs = lines.filter((l) => l.trim().startsWith('- ref:')).map((l) => l.split('ref:')[1].trim());
      if (agentRefs.length > 0) setAgents(agentRefs);
    } catch { /* fallback */ }
    setShowVersions(false);
  };

  const handleRun = async (stream: boolean) => {
    setError('');
    setIsRunning(true);
    try {
      let parsedInput = {};
      try { parsedInput = JSON.parse(inputData); } catch { /* */ }
      if (stream) {
        navigate('/app/workflows/run', { state: { yaml, inputData: parsedInput } });
        return;
      }
      await apiFetch(`${API.workflow}/workflows/run`, {
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
        <div className="flex gap-2">
          <button onClick={() => setShowSaved(!showSaved)} className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50">
            📂 Saved ({savedWorkflows?.length ?? 0})
          </button>
          <button onClick={() => navigate('/app/workflows')} className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50">
            ← Runs
          </button>
        </div>
      </div>

      {/* Saved workflows drawer */}
      {showSaved && savedWorkflows && savedWorkflows.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm mb-6">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">Saved Workflows</h3>
          <div className="grid grid-cols-3 gap-3">
            {savedWorkflows.map((w) => (
              <button
                key={w.name}
                onClick={() => { setShowVersions(true); setShowSaved(false); loadVersion(w.name, w.latest_version); }}
                className="text-left p-3 border border-gray-200 rounded-lg hover:border-blue-400 hover:bg-blue-50 transition-colors"
              >
                <div className="font-medium text-sm text-gray-900">{w.name}</div>
                <div className="text-xs text-gray-500 mt-1">{w.description || 'No description'}</div>
                <div className="mt-2 flex items-center gap-2">
                  <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs">v{w.latest_version}</span>
                  <span className="text-xs text-gray-400">{w.version_count} versions</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Templates */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm mb-6">
        <h3 className="text-sm font-semibold text-gray-900 mb-3">Quick Start Templates</h3>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {TEMPLATES.map((t) => (
            <button key={t.name} onClick={() => applyTemplate(t)} className="text-left p-3 border border-gray-200 rounded-lg hover:border-blue-400 hover:bg-blue-50 transition-colors">
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
        <div className="col-span-2 space-y-5">
          {/* Config */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Workflow Configuration</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Workflow Name</label>
                <input value={name} onChange={(e) => setName(e.target.value)} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Namespace</label>
                <input value={namespace} onChange={(e) => setNamespace(e.target.value)} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
            </div>
          </div>

          {/* Topology */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Topology</h3>
            <div className="grid grid-cols-2 gap-3">
              {TOPOLOGIES.map((t) => (
                <button key={t.value} onClick={() => { setTopology(t.value); if (t.value !== 'graph') setEdges([]); }}
                  className={`text-left p-3 border-2 rounded-lg transition-all ${topology === t.value ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300'}`}>
                  <div className="flex items-center gap-2"><span className="text-lg">{t.icon}</span><span className="font-medium text-sm text-gray-900">{t.label}</span></div>
                  <p className="text-xs text-gray-500 mt-1">{t.desc}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Agents */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-900">
                Agents {topology === 'hierarchical' && <span className="text-xs text-gray-400 font-normal ml-2">(first = supervisor)</span>}
              </h3>
              <button onClick={addAgent} className="text-xs text-blue-600 hover:text-blue-700 font-medium">+ Add Agent</button>
            </div>
            <div className="space-y-2">
              {agents.map((agent, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="text-xs text-gray-400 w-6 text-right">{i + 1}.</span>
                  {topology === 'hierarchical' && i === 0 && <span className="px-1.5 py-0.5 bg-amber-100 text-amber-700 rounded text-xs font-medium">Sup</span>}
                  {availableAgents && availableAgents.length > 0 ? (
                    <select value={agent} onChange={(e) => updateAgent(i, e.target.value)} className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500">
                      <option value="">Select agent...</option>
                      {availableAgents.map((a) => <option key={a.name} value={a.name}>{a.name} ({a.framework})</option>)}
                    </select>
                  ) : (
                    <input value={agent} onChange={(e) => updateAgent(i, e.target.value)} placeholder="agent-name" className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" />
                  )}
                  {agents.length > 1 && <button onClick={() => removeAgent(i)} className="text-red-400 hover:text-red-600 text-sm">✕</button>}
                </div>
              ))}
            </div>
          </div>

          {/* Visual Graph Editor */}
          {topology === 'graph' && validAgents.length >= 2 && (
            <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-900 mb-3">Graph Editor</h3>
              <GraphCanvas
                agents={validAgents}
                edges={edges}
                onAddEdge={addEdge}
                onRemoveEdge={removeEdge}
              />
              {/* Edge condition editor */}
              {edges.length > 0 && (
                <div className="mt-3">
                  <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Edge Conditions</h4>
                  {edges.map((e, i) => (
                    <div key={i} className="flex items-center gap-2 mb-1">
                      <span className="text-xs text-blue-600 font-medium">{e.from} → {e.to}</span>
                      <input
                        value={e.condition}
                        onChange={(ev) => updateEdgeCondition(i, ev.target.value)}
                        placeholder="condition (optional)"
                        className="flex-1 px-2 py-1 border border-gray-200 rounded text-xs font-mono outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* HITL */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-900 mb-2">Human-in-the-Loop</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Approval Gate</label>
                <select value={hitlGate} onChange={(e) => setHitlGate(e.target.value)} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500">
                  <option value="">None</option>
                  {validAgents.map((a) => <option key={a} value={a}>{a}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Timeout (s)</label>
                <input type="number" value={hitlTimeout} onChange={(e) => setHitlTimeout(Number(e.target.value))} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
            </div>
          </div>

          {/* Input Data */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-900 mb-2">Input Data (JSON)</h3>
            <textarea value={inputData} onChange={(e) => setInputData(e.target.value)} rows={3} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
        </div>

        {/* Right sidebar */}
        <div className="space-y-5">
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm sticky top-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-900">Generated YAML</h3>
              <button onClick={() => setShowYaml(!showYaml)} className="text-xs text-blue-600">{showYaml ? 'Hide' : 'Show'}</button>
            </div>
            {showYaml && (
              <pre className="bg-gray-900 text-green-400 p-3 rounded-lg text-xs font-mono overflow-auto max-h-60 mb-4 whitespace-pre-wrap">{yaml}</pre>
            )}
            <div className="space-y-2 mb-4">
              <div className="flex justify-between text-sm"><span className="text-gray-500">Topology</span><span className="font-medium">{topology}</span></div>
              <div className="flex justify-between text-sm"><span className="text-gray-500">Agents</span><span className="font-medium">{validAgents.length}</span></div>
              {topology === 'graph' && <div className="flex justify-between text-sm"><span className="text-gray-500">Edges</span><span className="font-medium">{edges.length}</span></div>}
              {hitlGate && <div className="flex justify-between text-sm"><span className="text-gray-500">HITL Gate</span><span className="font-medium text-amber-600">{hitlGate}</span></div>}
            </div>

            {error && <p className="text-sm text-red-600 mb-3">{error}</p>}

            <div className="space-y-2 mb-4">
              <button onClick={() => handleRun(true)} disabled={isRunning || validAgents.length === 0} className="w-full px-4 py-2.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
                ▶ Run with Live Stream
              </button>
              <button onClick={() => handleRun(false)} disabled={isRunning || validAgents.length === 0} className="w-full px-4 py-2 border border-gray-300 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50 disabled:opacity-50">
                {isRunning ? 'Running...' : 'Run (Blocking)'}
              </button>
            </div>

            {/* Save version */}
            <div className="border-t border-gray-200 pt-4">
              <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Save Version</h4>
              <input value={saveDesc} onChange={(e) => setSaveDesc(e.target.value)} placeholder="Version description..." className="w-full px-3 py-1.5 border border-gray-300 rounded-lg text-xs outline-none focus:ring-1 focus:ring-blue-500 mb-2" />
              <button
                onClick={() => saveMut.mutate()}
                disabled={saveMut.isPending || validAgents.length === 0}
                className="w-full px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg text-xs font-medium hover:bg-gray-200 disabled:opacity-50"
              >
                {saveMut.isPending ? 'Saving...' : '💾 Save Workflow Version'}
              </button>
              {saveMut.isSuccess && <p className="text-xs text-green-600 mt-1">Saved!</p>}
            </div>

            {validAgents.length === 0 && <p className="text-xs text-amber-600 mt-2">Add at least one agent</p>}
          </div>
        </div>
      </div>
    </div>
  );
}
