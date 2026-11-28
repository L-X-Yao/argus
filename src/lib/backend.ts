/**
 * Backend URL resolver.
 *
 * The page is always served by the backend itself, or by the Vite dev server,
 * which proxies /api and /ws to it. Every backend URL is same-origin, so
 * relative paths like "/api/ports" work directly.
 */

/** Base URL for HTTP API calls (no trailing slash). */
export const API_BASE: string = '';

/** WebSocket URL for the drone link. */
export function getWsUrl(): string {
  // Same origin: the handshake rides on the HttpOnly login cookie. A token in a
  // URL would leak into access logs and proxies.
  const loc = window.location;
  const proto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${loc.host}/ws`;
}

/** Resolve a relative API path (e.g. "/api/ports") to a full URL. */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

/**
 * 'rejected' is a wrong token. 'refused' is the backend turning this page away whatever the
 * token is: the address the page was opened from is not in its ARGUS_CORS_ORIGINS
 * (auth_middleware in backend/auth.py answers 403 "origin not allowed" before it looks at the
 * token). A 403 from anything else, a proxy in between, is not that.
 */
export type LoginResult = 'ok' | 'rejected' | 'refused';
const ORIGIN_REFUSED = 'origin not allowed';

/**
 * Exchange the access token for the session cookie that REST, tile and video
 * requests rely on. Rejects when the backend cannot be reached.
 */
/**
 * Ask the backend to start the bundled simulator if port 5770 is idle. The
 * backend answers once the port accepts, so the caller can connect right away.
 */
export async function startSimulator(): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fetch(apiUrl('/api/simulator/start'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
      signal: AbortSignal.timeout(15000),
    });
    const data = await res.json().catch(() => null);
    if (data?.ok === true) return { ok: true };
    return { ok: false, error: data?.error || `HTTP ${res.status}` };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

export async function login(token: string): Promise<LoginResult> {
  const res = await fetch(apiUrl('/api/auth/login'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
    signal: AbortSignal.timeout(5000),
  });
  const data = await res.json();
  if (res.status === 403 && data?.error === ORIGIN_REFUSED) return 'refused';
  return data?.ok === true ? 'ok' : 'rejected';
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
