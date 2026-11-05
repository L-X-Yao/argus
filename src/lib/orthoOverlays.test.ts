import { describe, it, expect, beforeEach, vi } from 'vitest';

const H = vi.hoisted(() => {
  const store: Record<string, string> = {};
  const storage = {
    full: false,
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => {
      if (storage.full) throw new Error('QuotaExceededError');
      store[k] = v;
    },
    clear: () => Object.keys(store).forEach((k) => delete store[k]),
  };
  vi.stubGlobal('localStorage', storage);
  return { storage };
});

import { addOrthoOverlay, ortho, removeOrthoOverlay, validOrthoBounds } from './orthoOverlays.svelte';

const bounds = { nwLat: 34.3, nwLon: 108.9, seLat: 34.2, seLon: 109 };
const overlay = { ...bounds, dataUrl: 'data:image/png;base64,AAAA', opacity: 0.8 };

describe('ortho overlays', () => {
  beforeEach(() => {
    ortho.overlays.length = 0;
    H.storage.clear();
    H.storage.full = false;
  });

  it('keeps an overlay between visits', () => {
    expect(addOrthoOverlay(overlay)).toBe(true);
    const saved = JSON.parse(localStorage.getItem('argus_ortho_overlays')!);
    expect(saved).toHaveLength(1);
    expect(saved[0].dataUrl).toBe(overlay.dataUrl);
  });

  it('reports an image the browser has no room for, and keeps it for the session', () => {
    H.storage.full = true;
    expect(addOrthoOverlay(overlay)).toBe(false);
    expect(ortho.overlays).toHaveLength(1);
  });

  it('removes an overlay', () => {
    addOrthoOverlay(overlay);
    removeOrthoOverlay(ortho.overlays[0].id);
    expect(ortho.overlays).toHaveLength(0);
    expect(JSON.parse(localStorage.getItem('argus_ortho_overlays')!)).toEqual([]);
  });

  it('accepts corners in the right order', () => {
    expect(validOrthoBounds(bounds)).toBe(true);
    expect(validOrthoBounds({ nwLat: -33, nwLon: 151, seLat: -34, seLon: 151.5 })).toBe(true);
  });

  it.each([
    ['swapped latitudes', { ...bounds, nwLat: 34.2, seLat: 34.3 }],
    ['swapped longitudes', { ...bounds, nwLon: 109, seLon: 108.9 }],
    ['a point, not an area', { nwLat: 34, nwLon: 108, seLat: 34, seLon: 108 }],
    ['latitude out of range', { ...bounds, nwLat: 91 }],
    ['longitude out of range', { ...bounds, seLon: 181 }],
    ['an empty field', { ...bounds, seLat: NaN }],
  ])('refuses %s', (_, b) => {
    expect(validOrthoBounds(b)).toBe(false);
  });
});
