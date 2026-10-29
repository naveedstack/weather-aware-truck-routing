/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8000' }, // Django; in production both are served from one origin
  },
  build: {
    // MapLibre gets its own file so app changes don't invalidate the cached map library.
    rolldownOptions: {
      output: { codeSplitting: { groups: [{ name: 'maplibre', test: /node_modules[\\/]maplibre-gl[\\/]/ }] } },
    },
    chunkSizeWarningLimit: 1100, // MapLibre alone is about 1 MB minified (about 290 kB gzipped)
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    env: { TZ: 'America/Chicago' }, // times in tests are shown in one fixed zone
  },
})
