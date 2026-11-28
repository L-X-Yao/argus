/** Which message to show for a failure code from `GET /api/video/last_error`. */
const KEYS: Record<string, string> = {
  refused: 'video.errRefused',
  timeout: 'video.errTimeout',
  auth: 'video.errAuth',
  notfound: 'video.errNotFound',
  unreachable: 'video.errUnreachable',
  server: 'video.errServer',
  protocol: 'video.errProtocol',
};

export function videoErrorKey(code: string | null | undefined): string {
  // The code comes from the backend. Object.hasOwn, not a truthiness check:
  // "constructor" is a member of every object and would name a key that does not exist.
  return (code && Object.hasOwn(KEYS, code) && KEYS[code]) || 'video.loadFail';
}
