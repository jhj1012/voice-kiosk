/// <reference types="vitest/config" />
import { createReadStream, statSync } from 'node:fs';
import { extname, join, normalize, resolve } from 'node:path';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig, type Plugin } from 'vite';

// In development the backend (uv run kiosk) runs on port 8765; Vite forwards to it.
const backend = 'http://127.0.0.1:8765';
const data = resolve(__dirname, '..', 'data');
const TYPES: Record<string, string> = {
  '.png': 'image/png',
  '.webp': 'image/webp',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webm': 'video/webm',
  '.mp4': 'video/mp4',
};

/** Menu images and the avatar straight from data/, so demo mode works without the backend. */
function dataFiles(): Plugin {
  return {
    name: 'kiosk-data-files',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const path = decodeURIComponent((req.url ?? '').split('?')[0]);
        const folder = path.startsWith('/images/')
          ? 'images'
          : path.startsWith('/avatar/')
            ? 'avatar'
            : null;
        if (!folder) return next();
        const file = normalize(join(data, folder, path.slice(folder.length + 2)));
        if (!file.startsWith(join(data, folder)) || !TYPES[extname(file)]) return next();
        try {
          const size = statSync(file).size;
          res.setHeader('Content-Type', TYPES[extname(file)]);
          res.setHeader('Content-Length', size);
          createReadStream(file).pipe(res);
        } catch {
          res.statusCode = 404;
          res.end();
        }
      });
    },
  };
}

export default defineConfig({
  plugins: [svelte(), dataFiles()],
  server: {
    proxy: {
      '/ws': { target: backend, ws: true },
      '/api': backend,
    },
  },
  test: { include: ['src/**/*.test.ts'] },
});
