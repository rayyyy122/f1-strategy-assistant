import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: ['.loca.lt', '.trycloudflare.com'],
    proxy: {
      '/api': {
        target: 'https://todd-bowling-forecast-upgrading.trycloudflare.com',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})