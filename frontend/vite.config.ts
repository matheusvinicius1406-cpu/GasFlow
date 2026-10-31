import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath } from 'node:url'

const srcDir = fileURLToPath(new URL('./src', import.meta.url))

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': srcDir,
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Namespaces que o backend serve COM /api (/api/v1/*, /api/driver/*):
      // passam adiante sem rewrite. Precisam vir ANTES de /api, que é
      // casado por prefixo e venceria se viesse primeiro.
      '/api/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api/driver': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Demais rotas: strip /api → backend recebe /clients/*, /orders/* etc.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      // WebSocket realtime (backend /ws) — must be upgraded, not rewritten
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
