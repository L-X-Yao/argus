import { describe, it, expect, vi } from 'vitest';
import { readFileSync } from 'node:fs';

// The service worker is plain JavaScript in public/, so it runs here against stand-ins.
function loadWorker(fetchTile: (url: string) => Promise<Response>, stored: string[] = []) {
  const handlers: Record<string, (e: unknown) => void> = {};
  // What the app cache held before, and every put since with the cache it went to.
  const kept = new Set(stored);
  const puts: [string, string][] = [];
  const cacheNamed = (name: string) => ({
    match: async () => undefined,
    put: async (r: { url: string } | string) => void puts.push([name, typeof r === 'string' ? r : r.url]),
    keys: async () => (name.startsWith('argus-gcs') ? [...kept].map((url) => ({ url })) : []),
    delete: async (r: { url: string }) => kept.delete(r.url),
  });
  const scope = {
    addEventListener: (type: string, fn: (e: unknown) => void) => (handlers[type] = fn),
    skipWaiting: () => {},
    clients: { claim: () => {} },
    location: { origin: 'http://x' },
  };
  const caches = {
    open: async (name: string) => cacheNamed(name),
    match: async () => undefined,
    keys: async () => [],
    delete: async () => true,
  };
  const source = readFileSync('public/sw.js', 'utf-8');
  new Function('self', 'caches', 'fetch', source)(scope, caches, (r: { url: string }) => fetchTile(r.url));
  const request = (url: string) => {
    let response: Promise<Response> = Promise.reject(new Error('not answered'));
    response.catch(() => {});
    handlers.fetch({
      request: { url, signal: undefined },
      respondWith: (r: Promise<Response>) => (response = r),
    });
    return response;
  };
  return Object.assign(request, { handlers, kept, puts });
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

describe('other servers in the service worker', () => {
  const TERRAIN = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/10/800/400.png';

  it('are left to the browser: their answers are not kept', async () => {
    const asked: string[] = [];
    const request = loadWorker(async (url) => {
      asked.push(url);
      return new Response('x');
    });
    for (const url of ['https://example.com/assets/x.js', 'https://s3.amazonaws.com/some-other-bucket/1.png']) {
      await expect(request(url)).rejects.toThrow('not answered');
    }
    expect(asked).toEqual([]);
    expect(request.puts).toEqual([]);
  });

  it('keep the elevation tiles of the 3D view, in the cache that has a limit', async () => {
    const request = loadWorker(async () => new Response('x'));
    await request(TERRAIN);
    await request('http://x/assets/index-abc.js');
    // The app cache carries the version in its name: scripts/bump_version.sh.
    const which = () => request.puts.map(([cache, url]) => [cache.replace(/-v[\d.]+$/, ''), url]);
    await vi.waitFor(() =>
      expect(which()).toEqual([
        ['argus-tiles', TERRAIN],
        ['argus-gcs', 'http://x/assets/index-abc.js'],
      ]),
    );
  });

  it('lose what an earlier version kept of them in the app cache, when this one takes over', async () => {
    const request = loadWorker(async () => new Response('x'), [TERRAIN, 'http://x/', 'http://x/assets/index-abc.js']);
    let done: Promise<unknown> = Promise.resolve();
    request.handlers.activate({ waitUntil: (p: Promise<unknown>) => (done = p) });
    await done;
    expect([...request.kept].sort()).toEqual(['http://x/', 'http://x/assets/index-abc.js']);
  });
});
