import path from 'path';
import { defineConfig } from 'vite';
import { svelte, vitePreprocess } from '@sveltejs/vite-plugin-svelte';
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
        manualChunks(id: string) {
          if (id.includes('node_modules/svelte/')) {
            return 'vendor-svelte';
          }
          if (id.includes('node_modules/clsx') || id.includes('node_modules/tailwind-merge') ||
              id.includes('node_modules/bits-ui') || id.includes('node_modules/@lucide/svelte')) {
            return 'vendor-ui';
          }
          if (id.includes('node_modules/maplibre-gl')) {
            return 'vendor-maplibre';
          }
          if (id.includes('src/lib/mavlink/')) {
            return 'mavlink';
          }
          const toolPaths = ['dflog', 'survey', 'gcj02', 'flightDb', 'plugins', 'units', 'branding'];
          if (toolPaths.some(p => id.includes(`src/lib/${p}`))) {
            return 'tools';
          }
        },
      },
    },
  },
  plugins: [tailwindcss(), svelte({ preprocess: vitePreprocess() })],
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
