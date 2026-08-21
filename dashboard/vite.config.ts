import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    include: ['@dagrejs/dagre']
  },
  server: {
    proxy: {
      // Same-origin access to the Nginx-fronted backend (avoids CORS in dev;
      // in a deployed setup the dashboard is served behind the same proxy).
      '/history': 'http://localhost:80',
      '/traces': 'http://localhost:80',
      '/ingest': 'http://localhost:80',
      '/ws': {
        target: 'ws://localhost:80',
        ws: true
      }
    }
  }
})
