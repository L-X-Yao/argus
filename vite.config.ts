import path from 'path';
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  define: {
    __BUILD_DATE__: JSON.stringify(new Date().toISOString().slice(0, 10)),
  },
  test: {
    include: ['src/**/*.test.ts'],
  },
  build: {
    chunkSizeWarningLimit: 300,
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-ui': ['clsx', 'tailwind-merge', 'bits-ui'],
          'vendor-icons': ['@lucide/svelte'],
          'tools': [
            './src/lib/dflog.ts',
            './src/lib/survey.ts',
            './src/lib/gcj02.ts',
            './src/lib/flightDb.ts',
            './src/lib/plugins.ts',
            './src/lib/units.ts',
            './src/lib/branding.ts',
          ],
        },
      },
    },
  },
  plugins: [tailwindcss(), svelte()],
  resolve: {
    alias: {
      $lib: path.resolve('./src/lib'),
    },
  },
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
