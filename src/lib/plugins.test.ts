import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('./stores.svelte', () => ({
  app: { drone: {}, waypoints: [] },
  addToast: vi.fn(),
}));
vi.mock('./ws', () => ({
  sendCommand: vi.fn(),
}));

import { getPlugins, createPluginAPI, unloadPlugin } from './plugins';

describe('plugins', () => {
  it('getPlugins returns an array', () => {
    const plugins = getPlugins();
    expect(Array.isArray(plugins)).toBe(true);
  });

  it('createPluginAPI returns an object with version and event methods', () => {
    const api = createPluginAPI();
    expect(api.version).toBe('3.3.0');
    expect(typeof api.subscribe).toBe('function');
    expect(typeof api.emit).toBe('function');
  });

  it('unloadPlugin on a non-existent name does not throw', () => {
    expect(() => unloadPlugin('nonexistent_plugin_xyz')).not.toThrow();
  });

  it('createPluginAPI emit and subscribe roundtrip works', () => {
    // window.addEventListener / dispatchEvent are available in vitest
    // node environment via globalThis (jsdom not required for EventTarget)
    const listeners: Record<string, Function[]> = {};
    vi.stubGlobal('window', {
      addEventListener: (ev: string, cb: Function) => {
        (listeners[ev] ??= []).push(cb);
      },
      dispatchEvent: (ev: any) => {
        for (const cb of listeners[ev.type] ?? []) cb(ev);
      },
    });

    const api = createPluginAPI();
    let received: any = null;
    api.subscribe('test-roundtrip', (data: any) => { received = data; });
    api.emit('test-roundtrip', { hello: 'world' });
    expect(received).toEqual({ hello: 'world' });

    vi.unstubAllGlobals();
  });
});
