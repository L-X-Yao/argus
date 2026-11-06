/**
 * Backend URL resolver.
 *
 * In browser mode (vite dev / python run.py), the backend is on the same
 * origin, so relative paths like "/api/ports" work directly.
 *
 * In Tauri desktop mode, the webview is served from a custom protocol
 * (tauri://localhost or https://tauri.localhost), but the Python backend
 * runs on http://127.0.0.1:8100.  All API / WebSocket URLs must be
 * resolved to that address.
 */

/** True when running inside a Tauri webview. */
export const isTauri: boolean = '__TAURI_INTERNALS__' in window;

/** Base URL for HTTP API calls (no trailing slash). */
export const API_BASE: string = isTauri ? 'http://127.0.0.1:8100' : '';

/** WebSocket URL for the drone link. */
export function getWsUrl(): string {
  let base: string;
  if (isTauri) {
    base = 'ws://127.0.0.1:8100/ws';
  } else {
    const loc = window.location;
    const proto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
    base = `${proto}//${loc.host}/ws`;
  }
  const token = typeof localStorage !== 'undefined' ? localStorage.getItem('argus_auth_token') : null;
  return token ? `${base}?token=${encodeURIComponent(token)}` : base;
}

/** Resolve a relative API path (e.g. "/api/ports") to a full URL. */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

/**
 * Exchange the access token for the session cookie that REST, tile and video
 * requests rely on. Resolves false for a rejected token, and rejects when the
 * backend cannot be reached.
 */
export async function login(token: string): Promise<boolean> {
  const res = await fetch(apiUrl('/api/auth/login'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
    signal: AbortSignal.timeout(5000),
  });
  const data = await res.json();
  return data.ok === true;
}

// A map source for an .mbtiles file in the backend's mbtiles/ folder.
const OFFLINE_PREFIX = 'mbtiles:';
export const offlineSource = (file: string): string => OFFLINE_PREFIX + file;
export const isOfflineSource = (id: string): boolean => id.startsWith(OFFLINE_PREFIX);

export function tileUrl(style: string): string {
  if (!isOfflineSource(style)) return `${API_BASE}/api/tile/${style}/{z}/{x}/{y}`;
  const file = encodeURIComponent(style.slice(OFFLINE_PREFIX.length));
  return `${API_BASE}/api/mbtiles/${file}/{z}/{x}/{y}`;
}
