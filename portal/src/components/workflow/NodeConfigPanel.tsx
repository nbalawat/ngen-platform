import type { Node } from '@xyflow/react';
import type { AgentNodeData } from './AgentNode';

interface NodeConfigPanelProps {
  node: Node;
  onUpdate: (id: string, data: Partial<AgentNodeData>) => void;
  onDelete: (id: string) => void;
  onClose: () => void;
}

export default function NodeConfigPanel({ node, onUpdate, onDelete, onClose }: NodeConfigPanelProps) {
  const data = node.data as AgentNodeData;

  if (node.type === 'start' || node.type === 'end') {
    return (
      <div className="p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-bold text-gray-900">{node.type === 'start' ? 'Start Node' : 'End Node'}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">✕</button>
        </div>
        <p className="text-xs text-gray-500">
          {node.type === 'start'
            ? 'Workflow entry point. Connect to your first agent.'
            : 'Workflow exit. Connect from your final agent(s).'}
        </p>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-gray-900">Agent Configuration</h3>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600">✕</button>
      </div>

      {data.needsCreation && (
        <div className="p-2 bg-amber-50 border border-amber-200 rounded-lg">
          <p className="text-[10px] text-amber-700 font-medium">
            This agent will be auto-created when the workflow runs.
          </p>
        </div>
      )}

      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">Name</label>
        <input
          value={data.label || ''}
          onChange={(e) => onUpdate(node.id, { label: e.target.value })}
          className="w-full text-sm border border-gray-300 rounded-lg px-3 py-1.5"
        />
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">Role / Description</label>
        <textarea
          value={data.role || ''}
          onChange={(e) => onUpdate(node.id, { role: e.target.value })}
          className="w-full text-xs border border-gray-300 rounded-lg px-3 py-1.5 h-16 resize-none"
          placeholder="What does this agent do?"
        />
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">Tools</label>
        <div className="space-y-1">
          {(data.tools || []).map((tool, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="text-xs bg-blue-50 text-blue-700 px-2 py-1 rounded flex-1 truncate">{tool}</span>
              <button
                onClick={() => {
                  const newTools = (data.tools || []).filter((_, idx) => idx !== i);
                  onUpdate(node.id, { tools: newTools });
                }}
                className="text-red-400 hover:text-red-600 text-xs"
              >✕</button>
            </div>
          ))}
        </div>
      </div>

      <div className="pt-3 border-t border-gray-100">
        <button
          onClick={() => onDelete(node.id)}
          className="w-full px-3 py-2 bg-red-50 text-red-600 rounded-lg text-xs font-medium hover:bg-red-100"
        >
          Delete Node
        </button>
      </div>
    </div>
  );
}
