interface AgentNode {
  name: string;
  role?: string;
  tools?: string[];
  needs_creation?: boolean;
}

interface Edge {
  from: string;
  to: string;
  condition?: string;
}

interface WorkflowFlowViewProps {
  topology: string;
  agents: AgentNode[];
  edges?: Edge[];
  activeAgent?: string;
  onAgentClick?: (name: string) => void;
  onRemoveAgent?: (index: number) => void;
  className?: string;
}

const NODE_W = 160;
const NODE_H = 64;
const GAP_X = 80;
const GAP_Y = 80;
const PAD = 40;

function AgentNodeBox({
  agent, x, y, isActive, isSupervisor, onClick, onRemove,
}: {
  agent: AgentNode; x: number; y: number;
  isActive?: boolean; isSupervisor?: boolean;
  onClick?: () => void; onRemove?: () => void;
}) {
  return (
    <g onClick={onClick} style={{ cursor: onClick ? 'pointer' : 'default' }}>
      <rect
        x={x} y={y} width={NODE_W} height={NODE_H} rx={12}
        fill={isActive ? '#EFF6FF' : '#FFFFFF'}
        stroke={agent.needs_creation ? '#F59E0B' : isActive ? '#3B82F6' : '#D1D5DB'}
        strokeWidth={isActive ? 2.5 : 1.5}
        strokeDasharray={agent.needs_creation ? '6 3' : undefined}
      />
      <text x={x + NODE_W / 2} y={y + 24} textAnchor="middle" fontSize={13} fontWeight={600} fill="#1F2937">
        {agent.name}
      </text>
      <text x={x + NODE_W / 2} y={y + 42} textAnchor="middle" fontSize={10} fill="#6B7280">
        {agent.role ? (agent.role.length > 22 ? agent.role.slice(0, 22) + '...' : agent.role) : ''}
      </text>
      {isSupervisor && (
        <text x={x + NODE_W - 8} y={y + 16} textAnchor="end" fontSize={9} fill="#7C3AED" fontWeight={700}>
          SUP
        </text>
      )}
      {agent.needs_creation && (
        <text x={x + 8} y={y + 16} fontSize={9} fill="#D97706" fontWeight={600}>NEW</text>
      )}
      {onRemove && (
        <g onClick={(e) => { e.stopPropagation(); onRemove(); }} style={{ cursor: 'pointer' }}>
          <circle cx={x + NODE_W - 2} cy={y - 2} r={10} fill="#FEE2E2" stroke="#FCA5A5" />
          <text x={x + NODE_W - 2} y={y + 2} textAnchor="middle" fontSize={12} fill="#DC2626">×</text>
        </g>
      )}
    </g>
  );
}

function Arrow({ x1, y1, x2, y2, label }: { x1: number; y1: number; x2: number; y2: number; label?: string }) {
  const midX = (x1 + x2) / 2;
  const midY = (y1 + y2) / 2;
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const headLen = 10;

  return (
    <g>
      <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#9CA3AF" strokeWidth={1.5} />
      <polygon
        points={`${x2},${y2} ${x2 - headLen * Math.cos(angle - 0.4)},${y2 - headLen * Math.sin(angle - 0.4)} ${x2 - headLen * Math.cos(angle + 0.4)},${y2 - headLen * Math.sin(angle + 0.4)}`}
        fill="#9CA3AF"
      />
      {label && (
        <text x={midX} y={midY - 8} textAnchor="middle" fontSize={9} fill="#6B7280" fontStyle="italic">
          {label}
        </text>
      )}
    </g>
  );
}

export default function WorkflowFlowView({
  topology, agents, edges = [], activeAgent, onAgentClick, onRemoveAgent, className = '',
}: WorkflowFlowViewProps) {
  if (agents.length === 0) {
    return (
      <div className={`flex items-center justify-center py-16 text-gray-400 ${className}`}>
        <p>No agents in workflow</p>
      </div>
    );
  }

  if (topology === 'sequential') return renderSequential();
  if (topology === 'parallel') return renderParallel();
  if (topology === 'hierarchical') return renderHierarchical();
  return renderGraph();

  function renderSequential() {
    const totalW = agents.length * NODE_W + (agents.length - 1) * GAP_X + PAD * 2;
    const totalH = NODE_H + PAD * 2;

    return (
      <svg width="100%" viewBox={`0 0 ${totalW} ${totalH}`} className={className}>
        {agents.map((agent, i) => {
          const x = PAD + i * (NODE_W + GAP_X);
          const y = PAD;
          return (
            <g key={agent.name}>
              {i > 0 && (
                <Arrow
                  x1={PAD + (i - 1) * (NODE_W + GAP_X) + NODE_W}
                  y1={y + NODE_H / 2}
                  x2={x}
                  y2={y + NODE_H / 2}
                />
              )}
              <AgentNodeBox
                agent={agent} x={x} y={y}
                isActive={activeAgent === agent.name}
                onClick={() => onAgentClick?.(agent.name)}
                onRemove={onRemoveAgent ? () => onRemoveAgent(i) : undefined}
              />
            </g>
          );
        })}
      </svg>
    );
  }

  function renderParallel() {
    const totalW = NODE_W + PAD * 2 + 200;
    const totalH = agents.length * (NODE_H + GAP_Y / 2) + PAD * 2;
    const inputX = PAD;
    const inputY = totalH / 2;
    const outputX = totalW - PAD - 20;
    const outputY = totalH / 2;
    const agentX = PAD + 100;

    return (
      <svg width="100%" viewBox={`0 0 ${totalW} ${totalH}`} className={className}>
        {/* Input node */}
        <circle cx={inputX + 15} cy={inputY} r={15} fill="#E5E7EB" stroke="#9CA3AF" />
        <text x={inputX + 15} y={inputY + 4} textAnchor="middle" fontSize={10} fill="#374151">IN</text>

        {/* Output node */}
        <circle cx={outputX} cy={outputY} r={15} fill="#D1FAE5" stroke="#6EE7B7" />
        <text x={outputX} y={outputY + 4} textAnchor="middle" fontSize={10} fill="#065F46">OUT</text>

        {agents.map((agent, i) => {
          const y = PAD + i * (NODE_H + GAP_Y / 2);
          return (
            <g key={agent.name}>
              <Arrow x1={inputX + 30} y1={inputY} x2={agentX} y2={y + NODE_H / 2} />
              <AgentNodeBox
                agent={agent} x={agentX} y={y}
                isActive={activeAgent === agent.name}
                onClick={() => onAgentClick?.(agent.name)}
                onRemove={onRemoveAgent ? () => onRemoveAgent(i) : undefined}
              />
              <Arrow x1={agentX + NODE_W} y1={y + NODE_H / 2} x2={outputX - 15} y2={outputY} />
            </g>
          );
        })}
      </svg>
    );
  }

  function renderHierarchical() {
    if (agents.length === 0) return null;
    const supervisor = agents[0];
    const workers = agents.slice(1);
    const totalW = Math.max(workers.length, 1) * (NODE_W + GAP_X) + PAD * 2;
    const totalH = NODE_H * 2 + GAP_Y + PAD * 2;
    const supX = totalW / 2 - NODE_W / 2;
    const supY = PAD;

    return (
      <svg width="100%" viewBox={`0 0 ${totalW} ${totalH}`} className={className}>
        <AgentNodeBox
          agent={supervisor} x={supX} y={supY} isSupervisor
          isActive={activeAgent === supervisor.name}
          onClick={() => onAgentClick?.(supervisor.name)}
        />
        {workers.map((agent, i) => {
          const x = PAD + i * (NODE_W + GAP_X);
          const y = supY + NODE_H + GAP_Y;
          return (
            <g key={agent.name}>
              <Arrow x1={supX + NODE_W / 2} y1={supY + NODE_H} x2={x + NODE_W / 2} y2={y} />
              <AgentNodeBox
                agent={agent} x={x} y={y}
                isActive={activeAgent === agent.name}
                onClick={() => onAgentClick?.(agent.name)}
                onRemove={onRemoveAgent ? () => onRemoveAgent(i + 1) : undefined}
              />
            </g>
          );
        })}
      </svg>
    );
  }

  function renderGraph() {
    // Simple grid layout for graph nodes
    const cols = Math.ceil(Math.sqrt(agents.length));
    const rows = Math.ceil(agents.length / cols);
    const totalW = cols * (NODE_W + GAP_X) + PAD * 2;
    const totalH = rows * (NODE_H + GAP_Y) + PAD * 2;

    const positions: Record<string, { x: number; y: number }> = {};
    agents.forEach((agent, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      positions[agent.name] = {
        x: PAD + col * (NODE_W + GAP_X),
        y: PAD + row * (NODE_H + GAP_Y),
      };
    });

    return (
      <svg width="100%" viewBox={`0 0 ${totalW} ${totalH}`} className={className}>
        {edges.map((edge, i) => {
          const from = positions[edge.from];
          const to = positions[edge.to];
          if (!from || !to) return null;
          return (
            <Arrow
              key={i}
              x1={from.x + NODE_W} y1={from.y + NODE_H / 2}
              x2={to.x} y2={to.y + NODE_H / 2}
              label={edge.condition}
            />
          );
        })}
        {agents.map((agent, i) => {
          const pos = positions[agent.name];
          return (
            <AgentNodeBox
              key={agent.name}
              agent={agent} x={pos.x} y={pos.y}
              isActive={activeAgent === agent.name}
              onClick={() => onAgentClick?.(agent.name)}
              onRemove={onRemoveAgent ? () => onRemoveAgent(i) : undefined}
            />
          );
        })}
      </svg>
    );
  }
}
