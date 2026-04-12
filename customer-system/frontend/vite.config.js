import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const BACKEND_URL = process.env.CUSTOMER_BACKEND_URL || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 3000,
    proxy: {
      '/auth': { target: BACKEND_URL, changeOrigin: true },
      '/tickets': { target: BACKEND_URL, changeOrigin: true },
      '/messages': { target: BACKEND_URL, changeOrigin: true },
      '/health': { target: BACKEND_URL, changeOrigin: true },
      '/ws': { target: BACKEND_URL, changeOrigin: true, ws: true },
    },
  },
})
