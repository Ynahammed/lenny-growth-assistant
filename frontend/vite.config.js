import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Backend origin for the dev proxy: override with BACKEND_ORIGIN when the
// backend runs somewhere else (e.g. Docker Compose service name).
const backendOrigin = process.env.BACKEND_ORIGIN || 'http://127.0.0.1:8001'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/api': {
        target: backendOrigin,
        changeOrigin: true
      }
    }
  }
})
