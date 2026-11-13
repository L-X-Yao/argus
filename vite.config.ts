import fs from 'fs';
import path from 'path';
import { defineConfig, loadEnv, type Plugin } from 'vite';
import { svelte, vitePreprocess } from '@sveltejs/vite-plugin-svelte';
import tailwindcss from '@tailwindcss/vite';

// Same source and fallback as backend/config.py, so the dev proxy still reaches
// a backend moved with ARGUS_PORT (shell or .env).
const envPort = Number(loadEnv('', process.cwd(), 'ARGUS_').ARGUS_PORT);
const backendPort = Number.isInteger(envPort) && envPort >= 1 && envPort <= 65535 ? envPort : 8100;

/**
 * The libraries bundled into dist/ are under MIT, ISC, BSD and Apache licenses. Each asks that
 * its notice goes along with every copy, and minifying drops the notices. This writes them to
 * dist/THIRD-PARTY-LICENSES.txt, from the modules that really went into the bundle, so the
 * list cannot fall behind package.json. scripts/build_package.py will not build a package
 * without the file.
 */
function thirdPartyLicenses(): Plugin {
  const marker = '/node_modules/';
  // Its stylesheet reset is in the bundle as CSS, which has no module of its own to find.
  const always = [path.resolve('node_modules/tailwindcss')];
  return {
    name: 'argus-third-party-licenses',
    apply: 'build',
    generateBundle(_options, bundle) {
      const roots = new Set<string>(always.map((dir) => dir.split(path.sep).join('/')));
      for (const chunk of Object.values(bundle)) {
        if (chunk.type !== 'chunk') continue;
        for (const id of chunk.moduleIds) {
          const file = id.replace(/^\0/, '').split('?')[0].split(path.sep).join('/');
          const at = file.lastIndexOf(marker);
          if (at < 0) continue;
          const parts = file.slice(at + marker.length).split('/');
          const name = parts[0].startsWith('@') ? `${parts[0]}/${parts[1]}` : parts[0];
          roots.add(file.slice(0, at + marker.length) + name);
        }
      }
      const entries = [...roots].map((dir) => {
        const pkg = JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf-8'));
        const texts = fs
          .readdirSync(dir)
          .filter((file) => /^(licen[cs]e|copying|notice)/i.test(file))
          .sort()
          .map((file) => fs.readFileSync(path.join(dir, file), 'utf-8').trim());
        const repo = typeof pkg.repository === 'string' ? pkg.repository : pkg.repository?.url;
        return {
          name: `${pkg.name}@${pkg.version}`,
          text: [
            `${pkg.name}@${pkg.version}`,
            `License: ${pkg.license ?? 'see below'}`,
            `Source: ${pkg.homepage ?? repo ?? `https://www.npmjs.com/package/${pkg.name}`}`,
            '',
            texts.length
              ? texts.join('\n\n')
              : '(The package ships no license file. Its license is the one named above.)',
          ].join('\n'),
        };
      });
      entries.sort((a, b) => a.name.localeCompare(b.name));
      const rule = '\n\n' + '-'.repeat(78) + '\n\n';
      this.emitFile({
        type: 'asset',
        fileName: 'THIRD-PARTY-LICENSES.txt',
        source:
          'Argus GCS web interface: third-party software in this build\n' +
          'See also THIRD_PARTY_NOTICES.md in the Argus repository or package.' +
          rule +
          entries.map((entry) => entry.text).join(rule) +
          '\n',
      });
    },
  };
}

// The version the page shows is the one the package has: scripts/bump_version.sh keeps
// package.json in step with the other files, and a copy written into the panel was left at
// 3.4.0 while the releases moved on.
const pkgVersion = JSON.parse(fs.readFileSync(new URL('./package.json', import.meta.url), 'utf-8')).version;

export default defineConfig({
  define: {
    __BUILD_DATE__: JSON.stringify(new Date().toISOString().slice(0, 10)),
    __APP_VERSION__: JSON.stringify(pkgVersion),
  },
  test: {
    include: ['src/**/*.test.ts'],
    coverage: {
      exclude: ['src/lib/fc/px4.ts'],
    },
  },
  build: {
    chunkSizeWarningLimit: 300,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes('node_modules/svelte/')) {
            return 'vendor-svelte';
          }
          if (
            id.includes('node_modules/clsx') ||
            id.includes('node_modules/tailwind-merge') ||
            id.includes('node_modules/bits-ui') ||
            id.includes('node_modules/@lucide/svelte')
          ) {
            return 'vendor-ui';
          }
          if (id.includes('node_modules/maplibre-gl')) {
            return 'vendor-maplibre';
          }
          if (id.includes('src/lib/mavlink/')) {
            return 'mavlink';
          }
          const toolPaths = ['dflog', 'survey', 'gcj02', 'flightDb', 'plugins', 'units', 'branding'];
          if (toolPaths.some((p) => id.includes(`src/lib/${p}`))) {
            return 'tools';
          }
        },
      },
    },
  },
  plugins: [tailwindcss(), svelte({ preprocess: vitePreprocess() }), thirdPartyLicenses()],
  resolve: {
    alias: {
      $lib: path.resolve('./src/lib'),
    },
  },
  server: {
    // Windows + Node >=17 may resolve localhost to ::1, but the backend binds
    // IPv4-only 127.0.0.1 (run.py --host default) — pin both sides to IPv4.
    // LAN debugging still works via `npm run dev -- --host 0.0.0.0`.
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/ws': {
        target: `ws://127.0.0.1:${backendPort}`,
        ws: true,
      },
      '/api': {
        target: `http://127.0.0.1:${backendPort}`,
      },
      '/health': {
        target: `http://127.0.0.1:${backendPort}`,
      },
    },
  },
});
