export const API = {
  tenant: '/api/tenant',
  registry: '/api/registry',
  gateway: '/api/gateway',
  workflow: '/api/workflow',
  governance: '/api/governance',
  mcp: '/api/mcp',
  onboard: '/api/onboard',
  metering: '/api/metering',
} as const;

export const queryKeys = {
  orgs: { all: ['orgs'] as const, detail: (id: string) => ['orgs', id] as const },
  models: { all: ['models'] as const, detail: (id: string) => ['models', id] as const },
  agents: { all: ['agents'] as const, detail: (n: string) => ['agents', n] as const, memory: (n: string) => ['agents', n, 'memory'] as const },
  workflows: { runs: ['workflows', 'runs'] as const, detail: (id: string) => ['workflows', 'runs', id] as const },
  policies: { all: ['policies'] as const, detail: (id: string) => ['policies', id] as const },
  servers: { all: ['servers'] as const, detail: (id: string) => ['servers', id] as const },
  tools: { all: ['tools'] as const, search: (q: string) => ['tools', 'search', q] as const },
  usage: { tenant: (id: string) => ['usage', id] as const, summary: ['usage', 'summary'] as const },
  budgets: { all: ['budgets'] as const, ns: (ns: string) => ['budgets', ns] as const },
  knowledge: {
    collections: (tenantId: string) => ['knowledge', 'collections', tenantId] as const,
    documents: (tenantId: string, collection?: string) => ['knowledge', 'documents', tenantId, collection ?? ''] as const,
  },
  health: ['health'] as const,
  memory: {
    platform: ['memory', 'platform'] as const,
    health: ['memory', 'health'] as const,
    agent: (name: string) => ['memory', 'agent', name] as const,
    agentEntries: (name: string, type: string) => ['memory', 'entries', name, type] as const,
    tenantUsage: (id: string) => ['memory', 'usage', id] as const,
    platformSummary: ['memory', 'platform-summary'] as const,
  },
};
