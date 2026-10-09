/// <reference types="vitest" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const API_TARGET = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Explicit IPv4 host so the dev server is reachable at 127.0.0.1:5173
    // (the default "localhost" can resolve to ::1 only on some machines).
    host: '127.0.0.1',
    // The browser only ever talks to the Vite origin; /api is proxied to FastAPI.
    // Images live in this app's public/ folder, so they are served by Vite itself.
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
});
