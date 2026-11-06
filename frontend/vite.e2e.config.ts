import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Dedicated offline backend: browser checks must never consume a developer's live AI budget.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: { '/api': { target: 'http://127.0.0.1:8100', changeOrigin: true } },
  },
})
