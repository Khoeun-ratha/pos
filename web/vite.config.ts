import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// The browser calls /api on this same address; Vite forwards it to the Python service.
const service = process.env.POS_SERVICE_URL ?? 'http://localhost:8000'
const proxy = {
  '/api': { target: service, changeOrigin: true },
  '/uploads': { target: service, changeOrigin: true }, // product photos
}

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: { host: '0.0.0.0', port: 8080, proxy },
  preview: { host: '0.0.0.0', port: 8080, proxy },
})
