/// <reference types="vitest/config" />
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vite';

// In development the backend (uv run kiosk) runs on port 8765; Vite forwards to it.
const backend = 'http://127.0.0.1:8765';

export default defineConfig({
  plugins: [svelte()],
  server: {
    proxy: {
      '/ws': { target: backend, ws: true },
      '/images': backend,
      '/api': backend,
    },
  },
  test: { include: ['src/**/*.test.ts'] },
});
