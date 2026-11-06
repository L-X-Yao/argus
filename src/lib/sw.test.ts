import { describe, it, expect, vi } from 'vitest';
import { readFileSync } from 'node:fs';

// The service worker is plain JavaScript in public/, so it runs here against stand-ins.
function loadWorker(fetchTile: (url: string) => Promise<Response>) {
  const handlers: Record<string, (e: unknown) => void> = {};
  const cache = { match: async () => undefined, put: async () => {}, keys: async () => [] };
  const scope = {
    addEventListener: (type: string, fn: (e: unknown) => void) => (handlers[type] = fn),
    skipWaiting: () => {},
    clients: { claim: () => {} },
  };
  const caches = { open: async () => cache, match: async () => undefined, keys: async () => [] };
  const source = readFileSync('public/sw.js', 'utf-8');
  new Function('self', 'caches', 'fetch', source)(scope, caches, (r: { url: string }) => fetchTile(r.url));
  return (url: string) => {
    let response: Promise<Response> = Promise.reject(new Error('not answered'));
    response.catch(() => {});
    handlers.fetch({
      request: { url, signal: undefined },
      respondWith: (r: Promise<Response>) => (response = r),
    });
    return response;
  };
}

describe('tiles in the service worker', () => {
  it('leave connections free for everything else', async () => {
    const pending: (() => void)[] = [];
    const asked: string[] = [];
    const request = loadWorker((url) => {
      asked.push(url);
      return new Promise((ok) => pending.push(() => ok(new Response('tile'))));
    });

    const tiles = Array.from({ length: 10 }, (_, i) => request(`http://x/api/tile/osm/1/0/${i}`));
    await vi.waitFor(() => expect(asked.length).toBe(3));
    await new Promise((r) => setTimeout(r, 20));
    expect(asked.length).toBe(3);

    while (pending.length > 0) {
      pending.shift()!();
      await new Promise((r) => setTimeout(r, 5));
    }
    await Promise.all(tiles);
    expect(asked.length).toBe(10);
  });

  it('keep going after a failed tile', async () => {
    const asked: string[] = [];
    const request = loadWorker(async (url) => {
      asked.push(url);
      throw new Error('no network');
    });
    await Promise.all(Array.from({ length: 6 }, (_, i) => request(`http://x/api/tile/osm/1/0/${i}`)));
    expect(asked.length).toBe(6);
  });
});
