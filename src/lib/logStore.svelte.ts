export const MAX_LOG_SIZE = 256 * 1024 * 1024;

export interface LogEntry {
  id: number;
  size: number;
  time_utc: number;
}

class LogState {
  list: LogEntry[] = $state([]);
  downloading: boolean = $state(false);
  progress: number = $state(0);
  downloadId: number = $state(-1);
  downloadedBytes: number = $state(0);
  downloadSpeed: string = $state('');
  _lastSpeedTime: number = 0;
  _lastSpeedBytes: number = 0;
  // Chunks received during a streaming download, stored as (offset, bytes).
  // Backend now sends ~64KB chunks rather than one giant base64 blob at end.
  _chunks: { ofs: number; bytes: Uint8Array }[] = [];
  _expectedSize: number = 0;
  _chunkBytes: number = 0;
}

export const logState = new LogState();

// The panel keys its rows by id, and a list with two rows of one id does not render. A link can
// deliver an entry twice: a second request for the list while the first is still arriving.
export function setLogList(logs: LogEntry[]) {
  logState.list = [...new Map(logs.map((log) => [log.id, log])).values()];
}

export function startDownload(id: number, size: number) {
  logState.downloading = true;
  logState.downloadId = id;
  logState.progress = 0;
  logState.downloadedBytes = 0;
  logState.downloadSpeed = '';
  logState._lastSpeedTime = 0;
  logState._lastSpeedBytes = 0;
  logState._chunks = [];
  logState._expectedSize = size;
  logState._chunkBytes = 0;
}

function _decodeB64(b64: string): Uint8Array {
  const raw = atob(b64);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

function _appendChunk(ofs: number, bytes: Uint8Array): boolean {
  // This page's row is not the transfer's authority: the backend sizes the log
  // from its own list, which another client may have refreshed since. Dropping
  // the tail there saved a zero-filled file reported as complete (post-release
  // review 2026-11-18). MAX_LOG_SIZE is the memory bound; a byte past it is
  // refused, and completeDownload refuses that file anyway.
  if (logState._chunkBytes + bytes.length > MAX_LOG_SIZE) return false;
  const end = ofs + bytes.length;
  if (end > logState._expectedSize) logState._expectedSize = end;
  const maxChunks = Math.max(1000, Math.ceil(logState._expectedSize / 90));
  if (logState._chunks.length >= maxChunks) {
    // Fresh slices can be much smaller than 90 bytes. Merge a touching one at the cap instead
    // of rejecting a valid overlap stream; normal 90-byte bursts never pay this copy at the cap.
    for (const [i, c] of logState._chunks.entries()) {
      const touchesLeft = c.ofs + c.bytes.length === ofs;
      const touchesRight = ofs + bytes.length === c.ofs;
      if (!touchesLeft && !touchesRight) continue;
      const merged = new Uint8Array(c.bytes.length + bytes.length);
      if (touchesLeft) {
        merged.set(c.bytes);
        merged.set(bytes, c.bytes.length);
      } else {
        merged.set(bytes);
        merged.set(c.bytes, bytes.length);
      }
      logState._chunks.splice(i, 1, { ofs: touchesLeft ? c.ofs : ofs, bytes: merged });
      logState._chunkBytes += bytes.length;
      return true;
    }
    return false;
  }
  logState._chunks.push({ ofs, bytes });
  logState._chunkBytes += bytes.length;
  return true;
}

export function appendLogChunk(id: number, ofs: number, b64data: string): boolean {
  if (id !== logState.downloadId) return false;
  return _appendChunk(ofs, _decodeB64(b64data));
}

/** WebSerial direct-mode path: LOG_DATA bytes arrive as raw Uint8Array, no
 *  base64 round-trip. Mirrors appendLogChunk but skips the atob() decode. */
export function appendLogChunkBinary(id: number, ofs: number, bytes: Uint8Array): boolean {
  if (id !== logState.downloadId) return false;
  // Copy so the underlying ArrayBuffer can be reused by the transport's
  // read buffer without corrupting accumulated chunks.
  const owned = new Uint8Array(bytes.length);
  owned.set(bytes);
  return _appendChunk(ofs, owned);
}

export function updateDownloadProgress(received: number, total: number) {
  logState.downloadedBytes = received;
  if (total > 0) {
    logState.progress = Math.round((received / total) * 100);
  }
  const now = performance.now();
  if (logState._lastSpeedTime === 0) {
    logState._lastSpeedTime = now;
    logState._lastSpeedBytes = received;
    return;
  }
  const dt = (now - logState._lastSpeedTime) / 1000;
  if (dt >= 1.0) {
    const db = received - logState._lastSpeedBytes;
    const bps = db / dt;
    if (bps >= 1024 * 1024) {
      logState.downloadSpeed = (bps / 1024 / 1024).toFixed(1) + ' MB/s';
    } else {
      logState.downloadSpeed = Math.round(bps / 1024) + ' KB/s';
    }
    logState._lastSpeedTime = now;
    logState._lastSpeedBytes = received;
  }
}

export function completeDownload(id: number, b64data: string | undefined, size: number): boolean {
  // The completion of another client's download is not ours to assemble: the
  // chunks were dropped by id and a size-sized zero buffer would be saved.
  if (id !== logState.downloadId) return true;
  if (size > MAX_LOG_SIZE) {
    cancelDownload();
    return false;
  }
  logState.downloading = false;
  logState.downloadId = -1;
  logState.progress = 100;
  logState.downloadSpeed = '';

  let bytes: Uint8Array;
  if (b64data && b64data.length > 0) {
    // Legacy path: backend sent the whole log in one base64 string.
    bytes = _decodeB64(b64data);
  } else {
    // Streaming path: assemble from the accumulated chunks. Sorting by ofs
    // tolerates out-of-order delivery, and we use `size` (or the largest
    // ofs+length, whichever is bigger) to size the buffer.
    let maxEnd = size;
    for (const c of logState._chunks) {
      const e = c.ofs + c.bytes.length;
      if (e > maxEnd) maxEnd = e;
    }
    if (maxEnd > MAX_LOG_SIZE) {
      cancelDownload();
      return false;
    }
    bytes = new Uint8Array(maxEnd);
    for (const c of logState._chunks) {
      bytes.set(c.bytes, c.ofs);
    }
  }
  logState._chunks = [];
  logState._expectedSize = 0;
  logState._chunkBytes = 0;

  if (bytes.length === 0) return true;
  // Cast through ArrayBuffer to placate the strict BlobPart typing in
  // TS ≥6 — Uint8Array<ArrayBufferLike> isn't directly assignable.
  const blob = new Blob([bytes.buffer as ArrayBuffer], { type: 'application/octet-stream' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `log_${id}.bin`;
  a.click();
  URL.revokeObjectURL(url);
  return true;
}

export function cancelDownload() {
  logState.downloading = false;
  logState.downloadId = -1;
  logState.progress = 0;
  logState.downloadSpeed = '';
  // Drop the accumulated chunks — could be tens of MB in flight.
  logState._chunks = [];
  logState._expectedSize = 0;
  logState._chunkBytes = 0;
}
