import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 5173,
    proxy: {
      '/ws': {
        target: 'ws://localhost:8100',
        ws: true,
      },
      '/api': {
        target: 'http://localhost:8100',
      },
      '/health': {
        target: 'http://localhost:8100',
      },
    },
  },
});
