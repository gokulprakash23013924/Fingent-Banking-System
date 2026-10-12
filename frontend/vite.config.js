import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/chat': 'http://127.0.0.1:8000',
      '/approvals': 'http://127.0.0.1:8000',
      '/customers': 'http://127.0.0.1:8000',
      '/accounts': 'http://127.0.0.1:8000',
      '/transactions': 'http://127.0.0.1:8000',
      '/bureau': 'http://127.0.0.1:8000',
      '/kyc': 'http://127.0.0.1:8000',
      '/alerts': 'http://127.0.0.1:8000',
      '/tools': 'http://127.0.0.1:8000',
      '/intents': 'http://127.0.0.1:8000',
      '/audit': 'http://127.0.0.1:8000',
      '/metrics': 'http://127.0.0.1:8000',
      '/admin': 'http://127.0.0.1:8000',
      '/simulate': 'http://127.0.0.1:8000',
      '/stream': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
})

