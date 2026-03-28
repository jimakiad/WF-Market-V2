import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://127.0.0.1:5000',
      '/factions': 'http://127.0.0.1:5000',
      '/process': 'http://127.0.0.1:5000',
      '/delete': 'http://127.0.0.1:5000',
      '/status': 'http://127.0.0.1:5000',
      '/logout': 'http://127.0.0.1:5000',
    },
  },
  build: {
    outDir: '../static/react',
    emptyOutDir: true,
  },
})
