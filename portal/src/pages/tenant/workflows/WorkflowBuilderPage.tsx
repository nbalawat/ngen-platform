import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../../../api/client';
import { API, queryKeys } from '../../../lib/constants';
import WorkflowCanvas, {
  generatedToFlow,
  flowToYaml,
} from '../../../components/workflow/WorkflowCanvas';
import { useWorkflowStream, type WorkflowEvent } from '../../../hooks/useWorkflowStream';
import type { Node, Edge } from '@xyflow/react';
import type { AgentNodeData } from '../../../components/workflow/AgentNode';

interface GeneratedAgent {
  name: string;
  role?: string;
  tools?: string[];
  needs_creation?: boolean;
}

interface GeneratedWorkflow {
  topology: string;
  agents: GeneratedAgent[];
  edges: { from: string; to: string; condition?: string }[];
  explanation: string;
  suggested_input: Record<string, unknown>;
  workflow_name: string;
  workflow_yaml: string;
}

const STEPS = ['Describe', 'Design', 'Test', 'Save'] as const;
type Step = typeof STEPS[number];

const EXAMPLE_PROMPTS = [
  { label: 'Research & Summarize', text: 'Research a topic using web search, analyze the findings, then write a comprehensive summary' },
  { label: 'Document Analysis', text: 'Parse a document, extract key data points, and generate a structured report' },
  { label: 'Customer Support Triage', text: 'Classify incoming support tickets and route them to the appropriate specialist agent' },
  { label: 'Parallel Review', text: 'Analyze a piece of text simultaneously for sentiment, key entities, and topic classification' },
];

/* ── Helpers ─────────────────────────────────────────────────────────── */

interface AgentOutput {
  name: string;
  thinking: string;
  text: string;
  tools: { name: string; output: string }[];
  status: 'pending' | 'running' | 'done' | 'error';
}

function buildAgentOutputs(events: WorkflowEvent[], agentNames: string[]): AgentOutput[] {
  const map = new Map<string, AgentOutput>();
  for (const name of agentNames) map.set(name, { name, thinking: '', text: '', tools: [], status: 'pending' });

  for (const ev of events) {
    const agentName = ev.agent_name || (ev.data?.agent_name as string) || '';
    if (!agentName) continue;
    if (!map.has(agentName)) map.set(agentName, { name: agentName, thinking: '', text: '', tools: [], status: 'pending' });
    const out = map.get(agentName)!;

    if (ev.type === 'thinking') { out.status = 'running'; out.thinking = String((ev.data as Record<string, unknown>)?.text || ''); }
    else if (ev.type === 'text_delta') { out.status = 'running'; out.text += String((ev.data as Record<string, unknown>)?.text || ''); }
    else if (ev.type === 'tool_call_start') { out.status = 'running'; out.tools.push({ name: String((ev.data as Record<string, unknown>)?.tool || ''), output: '' }); }
    else if (ev.type === 'tool_call_end') { const last = out.tools[out.tools.length - 1]; if (last) last.output = String((ev.data as Record<string, unknown>)?.output || '').slice(0, 300); }
    else if (ev.type === 'done' && agentName) out.status = 'done';
    else if (ev.type === 'error') out.status = 'error';
  }
  return Array.from(map.values());
}

function extractFinalOutput(result: unknown): string {
  if (!result || typeof result !== 'object') return '';
  const r = result as Record<string, unknown>;
  const keys = Object.keys(r);
  for (const key of keys.reverse()) {
    if (key.endsWith('_output') && typeof r[key] === 'object') {
      const out = r[key] as Record<string, unknown>;
      if (out.text) return String(out.text);
    }
  }
  if (r.text) return String(r.text);
  return JSON.stringify(result, null, 2);
}

/* ── Main Component ──────────────────────────────────────────────────── */

export function WorkflowBuilderPage() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const stream = useWorkflowStream();

  const [step, setStep] = useState<Step>('Describe');
  const [description, setDescription] = useState('');
  const [generated, setGenerated] = useState<GeneratedWorkflow | null>(null);

  // Canvas state — persists across steps
  const [canvasNodes, setCanvasNodes] = useState<Node[]>([]);
  const [canvasEdges, setCanvasEdges] = useState<Edge[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const [inputJson, setInputJson] = useState('{}');
  const [workflowName, setWorkflowName] = useState('');
  const [saveDesc, setSaveDesc] = useState('');
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);

  const { data: availableAgents = [] } = useQuery({
    queryKey: queryKeys.agents.all,
    queryFn: () => apiFetch<{ name: string; framework: string }[]>(`${API.workflow}/agents`),
  });

  const generateMut = useMutation({
    mutationFn: async () => {
      const agentNames = availableAgents.map((a: { name: string }) => a.name);
      return apiFetch<GeneratedWorkflow>(`${API.workflow}/workflows/generate`, {
        method: 'POST',
        body: JSON.stringify({
          description,
          available_agents: agentNames,
          available_tools: ['web-search/search', 'knowledge-base/search_docs', 'document-intelligence/parse_document'],
        }),
      });
    },
    onSuccess: (data) => {
      setGenerated(data);
      setWorkflowName(data.workflow_name || 'my-workflow');
      setInputJson(JSON.stringify(data.suggested_input || {}, null, 2));
      // Convert to React Flow nodes/edges
      const { nodes, edges } = generatedToFlow(data.agents, data.edges);
      setCanvasNodes(nodes);
      setCanvasEdges(edges);
      setStep('Design');
    },
  });

  const currentYaml = useMemo(
    () => flowToYaml(canvasNodes, canvasEdges, workflowName || 'workflow'),
    [canvasNodes, canvasEdges, workflowName],
  );

  const saveMut = useMutation({
    mutationFn: async () => {
      return apiFetch(`${API.workflow}/versions/workflows`, {
        method: 'POST',
        body: JSON.stringify({
          name: workflowName,
          yaml_content: currentYaml,
          description: saveDesc || description,
        }),
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.workflows.runs });
      nav('/app/workflows');
    },
  });

  const stepIndex = STEPS.indexOf(step);

  // Agent names from canvas for test step
  const agentNames = useMemo(
    () => canvasNodes.filter(n => n.type === 'agent').map(n => (n.data as AgentNodeData).label),
    [canvasNodes],
  );

  const agentOutputs = useMemo(
    () => buildAgentOutputs(stream.events, agentNames),
    [stream.events, agentNames],
  );

  const finalOutput = useMemo(() => extractFinalOutput(stream.result), [stream.result]);

  // Build execution-state nodes (with status) for test step
  const executionNodes = useMemo(() => {
    return canvasNodes.map(n => {
      if (n.type !== 'agent') return n;
      const d = n.data as AgentNodeData;
      const output = agentOutputs.find(a => a.name === d.label);
      return { ...n, data: { ...d, status: output?.status || 'idle' } };
    });
  }, [canvasNodes, agentOutputs]);

  return (
    <div className="space-y-4" style={{ maxWidth: '100%' }}>
      {/* Step indicator */}
      <div className="flex items-center justify-between bg-white border border-gray-200 rounded-xl px-6 py-3">
        {STEPS.map((s, i) => (
          <div key={s} className="flex items-center">
            <button onClick={() => { if (i <= stepIndex) setStep(s); }} disabled={i > stepIndex}
              className={`flex items-center gap-2 ${i <= stepIndex ? 'cursor-pointer' : 'cursor-not-allowed opacity-50'}`}>
              <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                i < stepIndex ? 'bg-green-100 text-green-700' : i === stepIndex ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-400'
              }`}>{i < stepIndex ? '✓' : i + 1}</div>
              <span className={`text-sm font-medium ${i === stepIndex ? 'text-blue-700' : 'text-gray-500'}`}>{s}</span>
            </button>
            {i < STEPS.length - 1 && <div className={`w-12 h-0.5 mx-2 ${i < stepIndex ? 'bg-green-400' : 'bg-gray-200'}`} />}
          </div>
        ))}
      </div>

      {/* ──── Step 1: Describe ──── */}
      {step === 'Describe' && (
        <div className="space-y-6">
          <div className="bg-white border border-gray-200 rounded-xl p-8">
            <h2 className="text-xl font-bold text-gray-900 mb-2">What should this workflow do?</h2>
            <p className="text-sm text-gray-500 mb-6">Describe in plain language. AI will design an initial flow that you can freely edit on the canvas.</p>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g., Research AI trends using web search, then analyze sentiment and extract entities in parallel, finally merge into a summary..."
              className="w-full h-32 border border-gray-300 rounded-xl px-4 py-3 text-sm resize-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
            <div className="flex justify-end mt-4">
              <button onClick={() => generateMut.mutate()} disabled={!description.trim() || generateMut.isPending}
                className="px-6 py-3 bg-blue-600 text-white rounded-xl text-sm font-semibold hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2">
                {generateMut.isPending
                  ? <><div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" /> AI is designing...</>
                  : <>Generate Workflow →</>}
              </button>
            </div>
            {generateMut.isError && <p className="text-sm text-red-600 mt-3">Error: {(generateMut.error as Error).message}</p>}
          </div>
          <div>
            <h3 className="text-sm font-medium text-gray-500 mb-3">Or start from an example:</h3>
            <div className="grid grid-cols-2 gap-3">
              {EXAMPLE_PROMPTS.map((ex) => (
                <button key={ex.label} onClick={() => setDescription(ex.text)}
                  className="text-left p-4 bg-white border border-gray-200 rounded-xl hover:border-blue-400 hover:bg-blue-50 transition">
                  <div className="text-sm font-semibold text-gray-900">{ex.label}</div>
                  <div className="text-xs text-gray-500 mt-1 line-clamp-2">{ex.text}</div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ──── Step 2: Design (Canvas Editor) ──── */}
      {step === 'Design' && (
        <div className="space-y-3">
          {generated?.explanation && (
            <div className="bg-blue-50 border border-blue-200 rounded-xl p-3 flex items-start gap-3">
              <span className="text-lg">🤖</span>
              <p className="text-sm text-blue-800">{generated.explanation} <span className="text-blue-600 font-medium">You can now freely edit — add nodes, draw edges, rearrange the flow.</span></p>
            </div>
          )}

          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden" style={{ height: '500px' }}>
            <WorkflowCanvas
              initialNodes={canvasNodes}
              initialEdges={canvasEdges}
              onNodesChange={setCanvasNodes}
              onEdgesChange={setCanvasEdges}
              selectedNodeId={selectedNodeId}
              onNodeSelect={setSelectedNodeId}
              availableAgents={availableAgents}
            />
          </div>

          <div className="flex items-center justify-between">
            <button onClick={() => setStep('Describe')} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">← Back</button>
            <div className="flex items-center gap-3">
              <span className="text-xs text-gray-400">{canvasNodes.filter(n => n.type === 'agent').length} agents · {canvasEdges.length} edges</span>
              <button onClick={() => setStep('Test')}
                disabled={canvasNodes.filter(n => n.type === 'agent').length < 2 || canvasEdges.length < 1}
                className="px-6 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-semibold hover:bg-blue-700 disabled:opacity-50">
                Test Workflow →
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ──── Step 3: Test ──── */}
      {step === 'Test' && (
        <div className="space-y-3">
          {/* Execution canvas (read-only) */}
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden" style={{ height: '280px' }}>
            <div className="flex items-center justify-between px-4 py-2 border-b border-gray-100 bg-gray-50">
              <span className="text-xs font-semibold text-gray-600">Execution Flow</span>
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                stream.status === 'completed' ? 'bg-green-100 text-green-700' :
                stream.status === 'running' ? 'bg-blue-100 text-blue-700 animate-pulse' :
                stream.status === 'failed' ? 'bg-red-100 text-red-700' :
                'bg-gray-100 text-gray-500'
              }`}>{stream.status === 'idle' ? 'Ready' : stream.status} {stream.status !== 'idle' && `· ${stream.elapsed}s`}</span>
            </div>
            <div style={{ height: 'calc(100% - 36px)' }}>
              <WorkflowCanvas
                initialNodes={executionNodes}
                initialEdges={canvasEdges}
                readOnly
              />
            </div>
          </div>

          {/* Input + Agent outputs */}
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-3">
              <div className="bg-white border border-gray-200 rounded-xl p-3">
                <h3 className="text-xs font-semibold text-gray-700 mb-2">Test Input</h3>
                <textarea value={inputJson} onChange={(e) => setInputJson(e.target.value)}
                  className="w-full h-20 font-mono text-[10px] border border-gray-200 rounded-lg p-2 resize-none" />
                <div className="mt-2">
                  {stream.status === 'idle' || stream.status === 'completed' || stream.status === 'failed' || stream.status === 'cancelled' ? (
                    <button onClick={() => {
                      let input = {};
                      try { input = JSON.parse(inputJson); } catch { /* */ }
                      stream.reset();
                      stream.start(currentYaml, input);
                    }} className="w-full px-3 py-2 bg-green-600 text-white rounded-lg text-xs font-semibold hover:bg-green-700">
                      ▶ Run Test
                    </button>
                  ) : (
                    <button onClick={() => stream.cancel()} className="w-full px-3 py-2 bg-red-600 text-white rounded-lg text-xs font-semibold hover:bg-red-700">■ Stop</button>
                  )}
                </div>
              </div>
            </div>

            <div className="col-span-2 space-y-2 max-h-[400px] overflow-y-auto">
              {stream.status === 'idle' && (
                <div className="bg-white border border-gray-200 rounded-xl p-6 text-center text-gray-400">
                  <p className="text-sm">Click "Run Test" to execute</p>
                </div>
              )}

              {agentOutputs.map((agent) => (
                <div key={agent.name} className={`bg-white border rounded-xl overflow-hidden ${
                  agent.status === 'running' ? 'border-blue-400' : agent.status === 'done' ? 'border-green-300' : 'border-gray-200'
                }`}>
                  <button onClick={() => setExpandedAgent(expandedAgent === agent.name ? null : agent.name)}
                    className="w-full flex items-center justify-between px-3 py-2 hover:bg-gray-50">
                    <div className="flex items-center gap-2">
                      <div className={`w-2 h-2 rounded-full ${
                        agent.status === 'running' ? 'bg-blue-500 animate-pulse' : agent.status === 'done' ? 'bg-green-500' : 'bg-gray-300'
                      }`} />
                      <span className="text-xs font-semibold text-gray-900">{agent.name}</span>
                      {agent.status === 'running' && <div className="animate-spin rounded-full h-3 w-3 border border-blue-500 border-t-transparent" />}
                    </div>
                    <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${
                      agent.status === 'done' ? 'bg-green-100 text-green-700' : agent.status === 'running' ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-500'
                    }`}>{agent.status}</span>
                  </button>
                  {(expandedAgent === agent.name || agent.status === 'running') && (agent.thinking || agent.text || agent.tools.length > 0) && (
                    <div className="px-3 pb-3 space-y-2 border-t border-gray-100">
                      {agent.thinking && <div className="mt-2 p-2 bg-purple-50 rounded-lg"><p className="text-[10px] text-purple-900">{agent.thinking}</p></div>}
                      {agent.tools.map((t, i) => (
                        <div key={i} className="p-2 bg-amber-50 rounded-lg">
                          <div className="text-[9px] font-bold text-amber-700 uppercase mb-0.5">Tool: {t.name}</div>
                          {t.output && <p className="text-[10px] text-amber-900 line-clamp-2">{t.output}</p>}
                        </div>
                      ))}
                      {agent.text && (
                        <div className="p-2 bg-blue-50 rounded-lg">
                          <div className="text-[10px] text-gray-800 whitespace-pre-wrap max-h-32 overflow-y-auto leading-relaxed">
                            {agent.text.length > 800 ? agent.text.slice(0, 800) + '\n...' : agent.text}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}

              {stream.status === 'completed' && finalOutput && (
                <div className="bg-green-50 border border-green-200 rounded-xl p-4">
                  <h4 className="text-xs font-bold text-green-800 mb-2">✅ Final Output</h4>
                  <div className="text-xs text-gray-800 whitespace-pre-wrap leading-relaxed max-h-64 overflow-y-auto bg-white rounded-lg p-3 border border-green-100">
                    {finalOutput}
                  </div>
                </div>
              )}

              {stream.error && (
                <div className="bg-red-50 border border-red-200 rounded-xl p-3">
                  <p className="text-xs text-red-700">{stream.error}</p>
                </div>
              )}
            </div>
          </div>

          <div className="flex justify-between">
            <button onClick={() => { stream.reset(); setStep('Design'); }} className="px-4 py-2 text-sm text-gray-600">← Back to Design</button>
            <button onClick={() => setStep('Save')} className="px-6 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-semibold hover:bg-blue-700">Save Workflow →</button>
          </div>
        </div>
      )}

      {/* ──── Step 4: Save ──── */}
      {step === 'Save' && (
        <div className="max-w-lg mx-auto">
          <div className="bg-white border border-gray-200 rounded-xl p-8 space-y-4">
            <h2 className="text-xl font-bold text-gray-900">Save Workflow</h2>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Workflow Name</label>
              <input value={workflowName} onChange={(e) => setWorkflowName(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
              <textarea value={saveDesc || description} onChange={(e) => setSaveDesc(e.target.value)}
                className="w-full h-16 border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none" />
            </div>
            <div className="bg-gray-50 rounded-lg p-3 text-sm">
              <div className="grid grid-cols-2 gap-1">
                <span className="text-gray-500">Agents:</span><span className="font-medium">{canvasNodes.filter(n => n.type === 'agent').length}</span>
                <span className="text-gray-500">Edges:</span><span className="font-medium">{canvasEdges.length}</span>
              </div>
            </div>
            <div className="flex justify-between pt-2">
              <button onClick={() => setStep('Test')} className="px-4 py-2 text-sm text-gray-600">← Back</button>
              <button onClick={() => saveMut.mutate()} disabled={!workflowName.trim() || saveMut.isPending}
                className="px-6 py-2.5 bg-green-600 text-white rounded-xl text-sm font-semibold hover:bg-green-700 disabled:opacity-50">
                {saveMut.isPending ? 'Saving...' : '✓ Save & Deploy'}
              </button>
            </div>
            {saveMut.isError && <p className="text-sm text-red-600">Error: {(saveMut.error as Error)?.message || 'Save failed'}</p>}
          </div>
        </div>
      )}
    </div>
  );
}
