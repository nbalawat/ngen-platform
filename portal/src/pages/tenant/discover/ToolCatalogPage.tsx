import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { queryKeys } from '../../../lib/constants';
import { mcpApi } from '../../../api/mcpApi';

export function ToolCatalogPage() {
  const [search, setSearch] = useState('');
  const [selectedTool, setSelectedTool] = useState<string | null>(null);
  const [invokeArgs, setInvokeArgs] = useState('{}');
  const [invokeServer, setInvokeServer] = useState('');
  const [invokeTool, setInvokeTool] = useState('');

  const { data: tools, isLoading } = useQuery({
    queryKey: search ? queryKeys.tools.search(search) : queryKeys.tools.all,
    queryFn: () => search ? mcpApi.searchTools(search) : mcpApi.listTools(),
  });

  const invokeMut = useMutation({
    mutationFn: () => {
      const args = JSON.parse(invokeArgs);
      return mcpApi.invoke(invokeServer, invokeTool, args);
    },
  });

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Tool Catalog</h1>
        <p className="text-sm text-gray-500 mt-1">Discover and test tools from MCP servers</p>
      </div>

      <div className="mb-4">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search tools by name or description..."
          className="w-96 px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>
      ) : !tools || tools.length === 0 ? (
        <div className="text-center py-20 bg-white rounded-xl border border-gray-200">
          <span className="text-4xl">🔧</span>
          <h3 className="mt-3 text-lg font-medium text-gray-900">No tools found</h3>
          <p className="mt-1 text-sm text-gray-500">Register an MCP server to see its tools here</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {tools.map((tool) => (
            <div key={tool.id} className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm hover:shadow-md transition-shadow">
              <div className="flex items-center justify-between mb-1">
                <h3 className="text-sm font-semibold text-gray-900">{tool.name}</h3>
                <span className="text-xs text-gray-400">on {tool.server_name}</span>
              </div>
              <p className="text-xs text-gray-500 mb-2">{tool.description}</p>
              {tool.parameters.length > 0 && (
                <div className="mb-2">
                  <p className="text-[10px] font-medium text-gray-400 uppercase mb-1">Parameters</p>
                  <div className="flex gap-1 flex-wrap">
                    {tool.parameters.map((p) => (
                      <span key={p.name} className={`text-[10px] px-1.5 py-0.5 rounded ${p.required ? 'bg-blue-50 text-blue-700' : 'bg-gray-50 text-gray-600'}`}>
                        {p.name}: {p.type}{p.required ? ' *' : ''}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {tool.tags.length > 0 && (
                <div className="flex gap-1 flex-wrap mb-2">
                  {tool.tags.map((tag) => (
                    <span key={tag} className="text-[10px] bg-purple-50 text-purple-700 px-1.5 py-0.5 rounded">#{tag}</span>
                  ))}
                </div>
              )}
              <button
                onClick={() => { setInvokeServer(tool.server_name); setInvokeTool(tool.name); setSelectedTool(tool.id); }}
                className="text-xs text-blue-600 hover:text-blue-800"
              >
                Try it &rarr;
              </button>
            </div>
          ))}
        </div>
      )}

      {selectedTool && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setSelectedTool(null)}>
          <div className="bg-white rounded-xl p-6 w-[500px] max-h-[80vh] overflow-y-auto shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-gray-900 mb-1">Invoke Tool</h3>
            <p className="text-sm text-gray-500 mb-4">{invokeServer} / {invokeTool}</p>
            <label className="block text-sm font-medium text-gray-700 mb-1">Arguments (JSON)</label>
            <textarea
              value={invokeArgs}
              onChange={(e) => setInvokeArgs(e.target.value)}
              rows={4}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono outline-none focus:ring-2 focus:ring-blue-500 mb-3"
            />
            <button
              onClick={() => invokeMut.mutate()}
              disabled={invokeMut.isPending}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 mb-3"
            >
              {invokeMut.isPending ? 'Invoking...' : 'Invoke'}
            </button>
            {invokeMut.data && (
              <div className="mt-3 p-3 bg-gray-50 rounded-lg">
                <p className="text-xs font-medium text-gray-500 mb-1">Result ({invokeMut.data.duration_ms?.toFixed(1)}ms)</p>
                <pre className="text-xs text-gray-800 whitespace-pre-wrap">{JSON.stringify(invokeMut.data.result, null, 2)}</pre>
                {invokeMut.data.error && <p className="text-xs text-red-600 mt-1">{invokeMut.data.error}</p>}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
