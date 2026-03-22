import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';

export interface AgentNodeData {
  label: string;
  role?: string;
  tools?: string[];
  needsCreation?: boolean;
  status?: 'idle' | 'running' | 'done' | 'error';
  [key: string]: unknown;
}

function AgentNodeComponent({ data, selected }: NodeProps) {
  const d = data as AgentNodeData;
  const status = d.status || 'idle';

  return (
    <div
      className={`px-4 py-3 rounded-xl border-2 bg-white shadow-sm min-w-[160px] max-w-[220px] transition-all ${
        status === 'running'
          ? 'border-blue-500 shadow-blue-100 shadow-md'
          : status === 'done'
          ? 'border-green-400 shadow-green-50'
          : status === 'error'
          ? 'border-red-400'
          : selected
          ? 'border-blue-500 shadow-md'
          : d.needsCreation
          ? 'border-amber-400 border-dashed'
          : 'border-gray-200'
      }`}
    >
      <Handle type="target" position={Position.Left}
        className="!w-3 !h-3 !bg-gray-300 !border-2 !border-white hover:!bg-blue-500" />

      <div className="flex items-center gap-2 mb-1">
        <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
          status === 'running' ? 'bg-blue-500 animate-pulse' :
          status === 'done' ? 'bg-green-500' :
          status === 'error' ? 'bg-red-500' :
          'bg-gray-300'
        }`} />
        <span className="text-sm font-semibold text-gray-900 truncate">{d.label}</span>
        {d.needsCreation && (
          <span className="text-[9px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded font-bold flex-shrink-0">NEW</span>
        )}
      </div>

      {d.role && (
        <p className="text-[10px] text-gray-500 line-clamp-2 leading-tight">{d.role}</p>
      )}

      {d.tools && d.tools.length > 0 && (
        <div className="flex gap-1 mt-1.5 flex-wrap">
          {d.tools.slice(0, 3).map((t) => (
            <span key={t} className="text-[8px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded">
              {t.split('/').pop()}
            </span>
          ))}
        </div>
      )}

      <Handle type="source" position={Position.Right}
        className="!w-3 !h-3 !bg-gray-300 !border-2 !border-white hover:!bg-blue-500" />
    </div>
  );
}

export const AgentNode = memo(AgentNodeComponent);

// Start/End marker nodes
function StartNodeComponent() {
  return (
    <div className="w-12 h-12 rounded-full bg-green-100 border-2 border-green-400 flex items-center justify-center text-xs font-bold text-green-700">
      Start
      <Handle type="source" position={Position.Right} className="!w-2.5 !h-2.5 !bg-green-500 !border-2 !border-white" />
    </div>
  );
}

function EndNodeComponent() {
  return (
    <div className="w-12 h-12 rounded-full bg-gray-100 border-2 border-gray-400 flex items-center justify-center text-xs font-bold text-gray-600">
      End
      <Handle type="target" position={Position.Left} className="!w-2.5 !h-2.5 !bg-gray-500 !border-2 !border-white" />
    </div>
  );
}

export const StartNode = memo(StartNodeComponent);
export const EndNode = memo(EndNodeComponent);
