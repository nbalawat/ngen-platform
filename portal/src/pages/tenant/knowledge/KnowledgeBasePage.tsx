import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../../../lib/constants';
import { knowledgeBaseApi } from '../../../api/knowledgeBaseApi';

const TENANT_ID = 'default'; // TODO: from auth context

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

const FILE_ICONS: Record<string, string> = {
  'text/plain': '📄',
  'text/markdown': '📝',
  'application/pdf': '📕',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '📘',
};

export default function KnowledgeBasePage() {
  const qc = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [activeCollection, setActiveCollection] = useState<string | null>(null);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showNewCollection, setShowNewCollection] = useState(false);
  const [newColName, setNewColName] = useState('');
  const [newColDesc, setNewColDesc] = useState('');
  const [uploadCollection, setUploadCollection] = useState('');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);

  // Data fetching
  const { data: collections = [], isLoading: colLoading } = useQuery({
    queryKey: queryKeys.knowledge.collections(TENANT_ID),
    queryFn: () => knowledgeBaseApi.listCollections(TENANT_ID),
    refetchInterval: 10000,
  });

  const { data: documents = [], isLoading: docLoading } = useQuery({
    queryKey: queryKeys.knowledge.documents(TENANT_ID, activeCollection ?? undefined),
    queryFn: () => knowledgeBaseApi.listDocuments(TENANT_ID, activeCollection ?? undefined),
    refetchInterval: 5000,
  });

  // Mutations
  const uploadMut = useMutation({
    mutationFn: async () => {
      if (!uploadFile) throw new Error('No file selected');
      const col = uploadCollection || 'default';
      return knowledgeBaseApi.uploadDocument(uploadFile, TENANT_ID, col);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.knowledge.documents(TENANT_ID) });
      qc.invalidateQueries({ queryKey: queryKeys.knowledge.collections(TENANT_ID) });
      setShowUploadModal(false);
      setUploadFile(null);
      setUploadCollection('');
    },
  });

  const deleteMut = useMutation({
    mutationFn: (docId: string) => knowledgeBaseApi.deleteDocument(docId, TENANT_ID),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.knowledge.documents(TENANT_ID) });
      qc.invalidateQueries({ queryKey: queryKeys.knowledge.collections(TENANT_ID) });
    },
  });

  const createColMut = useMutation({
    mutationFn: () => knowledgeBaseApi.createCollection(TENANT_ID, newColName, newColDesc),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.knowledge.collections(TENANT_ID) });
      setShowNewCollection(false);
      setNewColName('');
      setNewColDesc('');
    },
  });

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) {
      setUploadFile(file);
      setShowUploadModal(true);
    }
  };

  const totalDocs = documents.length;
  const totalSize = documents.reduce((s, d) => s + d.size_bytes, 0);
  const totalChunks = documents.reduce((s, d) => s + d.chunk_count, 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Knowledge Base</h1>
          <p className="text-sm text-gray-500 mt-1">
            Upload documents and organize them into collections for agent RAG retrieval
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => setShowNewCollection(true)}
            className="px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            New Collection
          </button>
          <button
            onClick={() => setShowUploadModal(true)}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700"
          >
            Upload Document
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Collections', value: collections.length, icon: '📁' },
          { label: 'Documents', value: totalDocs, icon: '📄' },
          { label: 'Total Size', value: formatBytes(totalSize), icon: '💾' },
          { label: 'Chunks Indexed', value: totalChunks.toLocaleString(), icon: '🔍' },
        ].map((s) => (
          <div key={s.label} className="bg-white border border-gray-200 rounded-xl p-4">
            <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
              <span>{s.icon}</span> {s.label}
            </div>
            <div className="text-2xl font-semibold text-gray-900">{s.value}</div>
          </div>
        ))}
      </div>

      {/* Main content */}
      <div className="flex gap-6">
        {/* Collections sidebar */}
        <div className="w-64 flex-shrink-0">
          <div className="bg-white border border-gray-200 rounded-xl p-4">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">Collections</h3>
            <button
              onClick={() => setActiveCollection(null)}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm mb-1 ${
                activeCollection === null
                  ? 'bg-blue-50 text-blue-700 font-medium'
                  : 'text-gray-600 hover:bg-gray-50'
              }`}
            >
              All Documents
            </button>
            {colLoading ? (
              <div className="px-3 py-2 text-sm text-gray-400">Loading...</div>
            ) : (
              collections.map((col) => (
                <button
                  key={col.name}
                  onClick={() => setActiveCollection(col.name)}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm mb-1 flex justify-between ${
                    activeCollection === col.name
                      ? 'bg-blue-50 text-blue-700 font-medium'
                      : 'text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  <span>📁 {col.name}</span>
                  <span className="text-xs text-gray-400">{col.document_count}</span>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Document list */}
        <div
          className={`flex-1 bg-white border-2 rounded-xl ${
            dragOver ? 'border-blue-400 bg-blue-50' : 'border-gray-200'
          }`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleFileDrop}
        >
          {docLoading ? (
            <div className="flex items-center justify-center py-20">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
            </div>
          ) : documents.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-gray-400">
              <span className="text-4xl mb-3">📂</span>
              <p className="text-lg font-medium">No documents yet</p>
              <p className="text-sm mt-1">
                Drag & drop files here or click "Upload Document"
              </p>
              <p className="text-xs mt-1">Supports: .txt, .md, .pdf, .docx</p>
            </div>
          ) : (
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">Document</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">Collection</th>
                  <th className="text-right px-4 py-3 text-xs font-medium text-gray-500 uppercase">Size</th>
                  <th className="text-right px-4 py-3 text-xs font-medium text-gray-500 uppercase">Chunks</th>
                  <th className="text-center px-4 py-3 text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="text-right px-4 py-3 text-xs font-medium text-gray-500 uppercase">Uploaded</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {documents.map((doc) => (
                  <tr key={doc.id} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span>{FILE_ICONS[doc.content_type] || '📄'}</span>
                        <span className="text-sm font-medium text-gray-900">{doc.original_name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">{doc.collection}</td>
                    <td className="px-4 py-3 text-sm text-gray-500 text-right">{formatBytes(doc.size_bytes)}</td>
                    <td className="px-4 py-3 text-sm text-gray-500 text-right">{doc.chunk_count}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                        doc.status === 'ready'
                          ? 'bg-green-100 text-green-700'
                          : doc.status === 'error'
                          ? 'bg-red-100 text-red-700'
                          : 'bg-yellow-100 text-yellow-700'
                      }`}>
                        {doc.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-400 text-right">{formatDate(doc.created_at)}</td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => {
                          if (confirm(`Delete "${doc.original_name}"?`)) {
                            deleteMut.mutate(doc.id);
                          }
                        }}
                        className="text-red-400 hover:text-red-600 text-sm"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setShowUploadModal(false)}>
          <div className="bg-white rounded-xl p-6 w-[500px] shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Upload Document</h2>

            {/* File picker */}
            <div
              className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer mb-4 ${
                uploadFile ? 'border-green-400 bg-green-50' : 'border-gray-300 hover:border-blue-400'
              }`}
              onClick={() => fileInputRef.current?.click()}
            >
              {uploadFile ? (
                <div>
                  <span className="text-2xl">✅</span>
                  <p className="text-sm font-medium text-gray-900 mt-2">{uploadFile.name}</p>
                  <p className="text-xs text-gray-500">{formatBytes(uploadFile.size)}</p>
                </div>
              ) : (
                <div>
                  <span className="text-3xl">📁</span>
                  <p className="text-sm text-gray-600 mt-2">Click to select or drag & drop</p>
                  <p className="text-xs text-gray-400 mt-1">.txt, .md, .pdf, .docx (max 50MB)</p>
                </div>
              )}
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,.md,.pdf,.docx"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) setUploadFile(f);
              }}
            />

            {/* Collection picker */}
            <label className="block text-sm font-medium text-gray-700 mb-1">Collection</label>
            <select
              value={uploadCollection}
              onChange={(e) => setUploadCollection(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm mb-4"
            >
              <option value="">default</option>
              {collections.map((c) => (
                <option key={c.name} value={c.name}>{c.name}</option>
              ))}
            </select>

            {/* Actions */}
            <div className="flex justify-end gap-3">
              <button
                onClick={() => { setShowUploadModal(false); setUploadFile(null); }}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800"
              >
                Cancel
              </button>
              <button
                onClick={() => uploadMut.mutate()}
                disabled={!uploadFile || uploadMut.isPending}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
              >
                {uploadMut.isPending ? 'Uploading...' : 'Upload'}
              </button>
            </div>

            {uploadMut.isError && (
              <p className="text-sm text-red-600 mt-3">
                Error: {(uploadMut.error as Error).message}
              </p>
            )}
          </div>
        </div>
      )}

      {/* New Collection Modal */}
      {showNewCollection && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setShowNewCollection(false)}>
          <div className="bg-white rounded-xl p-6 w-[400px] shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold text-gray-900 mb-4">New Collection</h2>

            <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <input
              value={newColName}
              onChange={(e) => setNewColName(e.target.value)}
              placeholder="e.g. product-docs"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm mb-3"
            />

            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <input
              value={newColDesc}
              onChange={(e) => setNewColDesc(e.target.value)}
              placeholder="Optional description"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm mb-4"
            />

            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowNewCollection(false)}
                className="px-4 py-2 text-sm text-gray-600"
              >
                Cancel
              </button>
              <button
                onClick={() => createColMut.mutate()}
                disabled={!newColName.trim() || createColMut.isPending}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
