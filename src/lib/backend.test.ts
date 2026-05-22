import { describe, it, expect, vi, beforeEach } from 'vitest';

describe('backend URL resolver', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it('apiUrl returns relative path in browser mode', async () => {
    vi.stubGlobal('window', { location: { protocol: 'http:', host: 'localhost:5173' } });
    const { apiUrl, API_BASE } = await import('./backend');
    expect(API_BASE).toBe('');
    expect(apiUrl('/api/ports')).toBe('/api/ports');
  });

  it('getWsUrl uses correct protocol for http', async () => {
    vi.stubGlobal('window', { location: { protocol: 'http:', host: 'localhost:5173' } });
    const { getWsUrl } = await import('./backend');
    const url = getWsUrl();
    expect(url).toBe('ws://localhost:5173/ws');
  });

  it('getWsUrl uses wss for https', async () => {
    vi.stubGlobal('window', { location: { protocol: 'https:', host: 'gcs.example.com' } });
    const { getWsUrl } = await import('./backend');
    const url = getWsUrl();
    expect(url).toBe('wss://gcs.example.com/ws');
  });

  it('detects Tauri mode via __TAURI_INTERNALS__', async () => {
    vi.stubGlobal('window', {
      __TAURI_INTERNALS__: {},
      location: { protocol: 'https:', host: 'tauri.localhost' },
    });
    const { isTauri, API_BASE, getWsUrl } = await import('./backend');
    expect(isTauri).toBe(true);
    expect(API_BASE).toBe('http://127.0.0.1:8100');
    expect(getWsUrl()).toBe('ws://127.0.0.1:8100/ws');
  });
});
