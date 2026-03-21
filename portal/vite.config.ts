import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3000,
    proxy: {
      '/api/tenant': { target: 'http://localhost:8000', rewrite: (p) => p.replace('/api/tenant', '') },
      '/api/registry': { target: 'http://localhost:8001', rewrite: (p) => p.replace('/api/registry', '') },
      '/api/gateway': { target: 'http://localhost:8002', rewrite: (p) => p.replace('/api/gateway', '') },
      '/api/workflow': { target: 'http://localhost:8003', rewrite: (p) => p.replace('/api/workflow', '') },
      '/api/governance': { target: 'http://localhost:8004', rewrite: (p) => p.replace('/api/governance', '') },
      '/api/mcp': { target: 'http://localhost:8005', rewrite: (p) => p.replace('/api/mcp', '') },
      '/api/onboard': { target: 'http://localhost:8006', rewrite: (p) => p.replace('/api/onboard', '') },
      '/api/metering': { target: 'http://localhost:8007', rewrite: (p) => p.replace('/api/metering', '') },
    },
  },
})
