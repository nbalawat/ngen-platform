import { useCallback, useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type Connection,
  type OnConnect,
  MarkerType,
  Panel,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from 'dagre';
import { AgentNode, StartNode, EndNode, type AgentNodeData } from './AgentNode';
import NodeConfigPanel from './NodeConfigPanel';

const nodeTypes = {
  agent: AgentNode,
  start: StartNode,
  end: EndNode,
};

const defaultEdgeOptions = {
  animated: false,
  markerEnd: { type: MarkerType.ArrowClosed, color: '#9CA3AF' },
  style: { stroke: '#9CA3AF', strokeWidth: 1.5 },
};

interface WorkflowCanvasProps {
  initialNodes: Node[];
  initialEdges: Edge[];
  readOnly?: boolean;
  selectedNodeId?: string | null;
  onNodesChange?: (nodes: Node[]) => void;
  onEdgesChange?: (edges: Edge[]) => void;
  onNodeSelect?: (nodeId: string | null) => void;
  availableAgents?: { name: string; framework?: string }[];
}

// Auto-layout using dagre
export function autoLayout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'LR', nodesep: 60, ranksep: 120 });

  nodes.forEach((node) => {
    const w = node.type === 'start' || node.type === 'end' ? 60 : 200;
    const h = node.type === 'start' || node.type === 'end' ? 60 : 80;
    g.setNode(node.id, { width: w, height: h });
  });

  edges.forEach((edge) => {
    g.setEdge(edge.source, edge.target);
  });

  dagre.layout(g);

  return nodes.map((node) => {
    const pos = g.node(node.id);
    const w = node.type === 'start' || node.type === 'end' ? 60 : 200;
    const h = node.type === 'start' || node.type === 'end' ? 60 : 80;
    return {
      ...node,
      position: { x: pos.x - w / 2, y: pos.y - h / 2 },
    };
  });
}

// Convert from generated workflow format to React Flow format
export function generatedToFlow(
  agents: { name: string; role?: string; tools?: string[]; needs_creation?: boolean }[],
  edges: { from: string; to: string; condition?: string }[],
): { nodes: Node[]; edges: Edge[] } {
  const flowNodes: Node[] = [];
  const flowEdges: Edge[] = [];

  // Add agent nodes
  agents.forEach((agent, i) => {
    flowNodes.push({
      id: agent.name,
      type: 'agent',
      position: { x: 200 + i * 280, y: 100 },
      data: {
        label: agent.name,
        role: agent.role || '',
        tools: agent.tools || [],
        needsCreation: agent.needs_creation || false,
        status: 'idle',
      } as AgentNodeData,
    });
  });

  // Add edges
  edges.forEach((edge) => {
    flowEdges.push({
      id: `${edge.from}-${edge.to}`,
      source: edge.from,
      target: edge.to,
      label: edge.condition || undefined,
      ...defaultEdgeOptions,
    });
  });

  // If no explicit edges but sequential agents, create implicit edges
  if (flowEdges.length === 0 && agents.length > 1) {
    for (let i = 0; i < agents.length - 1; i++) {
      flowEdges.push({
        id: `${agents[i].name}-${agents[i + 1].name}`,
        source: agents[i].name,
        target: agents[i + 1].name,
        ...defaultEdgeOptions,
      });
    }
  }

  // Auto-layout
  const laidOut = autoLayout(flowNodes, flowEdges);
  return { nodes: laidOut, edges: flowEdges };
}

// Convert React Flow state back to YAML
export function flowToYaml(nodes: Node[], edges: Edge[], workflowName: string): string {
  const agentNodes = nodes.filter((n) => n.type === 'agent');
  const lines = [
    'apiVersion: ngen.io/v1',
    'kind: Workflow',
    'metadata:',
    `  name: ${workflowName}`,
    'spec:',
    '  topology: graph',
    '  agents:',
  ];

  agentNodes.forEach((n) => {
    lines.push(`  - ref: ${(n.data as AgentNodeData).label || n.id}`);
  });

  if (edges.length > 0) {
    lines.push('  edges:');
    edges.forEach((e) => {
      const sourceNode = nodes.find((n) => n.id === e.source);
      const targetNode = nodes.find((n) => n.id === e.target);
      const sourceName = sourceNode?.type === 'agent' ? (sourceNode.data as AgentNodeData).label : e.source;
      const targetName = targetNode?.type === 'agent' ? (targetNode.data as AgentNodeData).label : e.target;
      lines.push(`  - from: ${sourceName}`);
      lines.push(`    to: ${targetName}`);
      if (e.label) {
        lines.push(`    condition: "${e.label}"`);
      }
    });
  }

  return lines.join('\n');
}

export default function WorkflowCanvas({
  initialNodes,
  initialEdges,
  readOnly = false,
  selectedNodeId,
  onNodesChange: onNodesExternal,
  onEdgesChange: onEdgesExternal,
  onNodeSelect,
  availableAgents = [],
}: WorkflowCanvasProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  const onConnect: OnConnect = useCallback(
    (params: Connection) => {
      setEdges((eds) => {
        const newEdges = addEdge({ ...params, ...defaultEdgeOptions }, eds);
        onEdgesExternal?.(newEdges);
        return newEdges;
      });
    },
    [setEdges, onEdgesExternal],
  );

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      onNodeSelect?.(node.id);
    },
    [onNodeSelect],
  );

  const onPaneClick = useCallback(() => {
    onNodeSelect?.(null);
  }, [onNodeSelect]);

  const handleAddAgent = useCallback(
    (agentName: string) => {
      const newNode: Node = {
        id: `agent-${Date.now()}`,
        type: 'agent',
        position: { x: 300 + nodes.length * 50, y: 200 + nodes.length * 30 },
        data: {
          label: agentName,
          role: '',
          tools: [],
          needsCreation: !availableAgents.some((a) => a.name === agentName),
          status: 'idle',
        } as AgentNodeData,
      };
      setNodes((nds) => {
        const updated = [...nds, newNode];
        onNodesExternal?.(updated);
        return updated;
      });
    },
    [nodes.length, setNodes, onNodesExternal, availableAgents],
  );

  const handleAutoLayout = useCallback(() => {
    setNodes((nds) => {
      const laidOut = autoLayout(nds, edges);
      onNodesExternal?.(laidOut);
      return laidOut;
    });
  }, [edges, setNodes, onNodesExternal]);

  const handleUpdateNode = useCallback(
    (id: string, dataUpdate: Partial<AgentNodeData>) => {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === id ? { ...n, data: { ...n.data, ...dataUpdate } } : n,
        ),
      );
    },
    [setNodes],
  );

  const handleDeleteNode = useCallback(
    (id: string) => {
      setNodes((nds) => {
        const updated = nds.filter((n) => n.id !== id);
        onNodesExternal?.(updated);
        return updated;
      });
      setEdges((eds) => {
        const updated = eds.filter((e) => e.source !== id && e.target !== id);
        onEdgesExternal?.(updated);
        return updated;
      });
      onNodeSelect?.(null);
    },
    [setNodes, setEdges, onNodesExternal, onEdgesExternal, onNodeSelect],
  );

  const selectedNode = useMemo(
    () => nodes.find((n) => n.id === selectedNodeId) || null,
    [nodes, selectedNodeId],
  );

  // Sync external node changes (e.g. status updates during execution)
  // This is handled by re-rendering with new initialNodes

  return (
    <div className="flex h-full">
      <div className={`${selectedNode && !readOnly ? 'w-[70%]' : 'w-full'} h-full relative`}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={readOnly ? undefined : onNodesChange}
          onEdgesChange={readOnly ? undefined : onEdgesChange}
          onConnect={readOnly ? undefined : onConnect}
          onNodeClick={onNodeClick}
          onPaneClick={onPaneClick}
          nodeTypes={nodeTypes}
          defaultEdgeOptions={defaultEdgeOptions}
          fitView
          nodesDraggable={!readOnly}
          nodesConnectable={!readOnly}
          elementsSelectable={true}
          deleteKeyCode={readOnly ? null : 'Backspace'}
          className="bg-gray-50"
        >
          <Background color="#e5e7eb" gap={20} />
          <Controls showInteractive={false} />
          <MiniMap
            nodeStrokeColor={(n) => {
              const d = n.data as AgentNodeData;
              if (d?.status === 'running') return '#3B82F6';
              if (d?.status === 'done') return '#22C55E';
              if (d?.status === 'error') return '#EF4444';
              return '#9CA3AF';
            }}
            nodeColor={(n) => {
              const d = n.data as AgentNodeData;
              if (d?.status === 'running') return '#DBEAFE';
              if (d?.status === 'done') return '#DCFCE7';
              return '#F9FAFB';
            }}
            style={{ height: 80, width: 120 }}
          />

          {/* Toolbar */}
          {!readOnly && (
            <Panel position="top-left" className="flex gap-2">
              <div className="relative group">
                <button className="px-3 py-1.5 bg-white border border-gray-300 rounded-lg text-xs font-medium text-gray-700 hover:bg-gray-50 shadow-sm">
                  + Add Agent
                </button>
                <div className="hidden group-hover:block absolute top-full left-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-50 min-w-[200px] max-h-48 overflow-y-auto">
                  {availableAgents.map((a) => (
                    <button
                      key={a.name}
                      onClick={() => handleAddAgent(a.name)}
                      className="w-full text-left px-3 py-2 text-xs hover:bg-blue-50 text-gray-700"
                    >
                      {a.name}
                    </button>
                  ))}
                  <div className="border-t border-gray-100">
                    <button
                      onClick={() => {
                        const name = prompt('New agent name:');
                        if (name) handleAddAgent(name.trim().replace(/\s+/g, '-').toLowerCase());
                      }}
                      className="w-full text-left px-3 py-2 text-xs text-blue-600 hover:bg-blue-50 font-medium"
                    >
                      + Create new agent...
                    </button>
                  </div>
                </div>
              </div>
              <button
                onClick={handleAutoLayout}
                className="px-3 py-1.5 bg-white border border-gray-300 rounded-lg text-xs font-medium text-gray-700 hover:bg-gray-50 shadow-sm"
              >
                Auto Layout
              </button>
            </Panel>
          )}
        </ReactFlow>
      </div>

      {/* Config panel */}
      {selectedNode && !readOnly && (
        <div className="w-[30%] border-l border-gray-200 bg-white overflow-y-auto">
          <NodeConfigPanel
            node={selectedNode}
            onUpdate={handleUpdateNode}
            onDelete={handleDeleteNode}
            onClose={() => onNodeSelect?.(null)}
          />
        </div>
      )}
    </div>
  );
}
