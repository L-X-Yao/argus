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
export const isTauri: boolean =
  '__TAURI_INTERNALS__' in window;

/** Base URL for HTTP API calls (no trailing slash). */
export const API_BASE: string = isTauri
  ? 'http://127.0.0.1:8100'
  : '';

/** WebSocket URL for the drone link. */
export function getWsUrl(): string {
  if (isTauri) {
    return 'ws://127.0.0.1:8100/ws';
  }
  const loc = window.location;
  const proto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${loc.host}/ws`;
}

/** Resolve a relative API path (e.g. "/api/ports") to a full URL. */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}
