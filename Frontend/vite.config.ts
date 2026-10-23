import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/pmtiles-proxy': {
        target: 'https://latest.protomaps.com',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/pmtiles-proxy/, ''),
      },
      '/nominatim-proxy': {
        target: 'https://nominatim.openstreetmap.org',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/nominatim-proxy/, ''),
        headers: {
          'User-Agent': 'QuackEarth-Frontend/1.0',
        },
      },
    },
  },
})
