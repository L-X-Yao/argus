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
}

export const logState = new LogState();

export function setLogList(logs: LogEntry[]) {
  logState.list = logs;
}

export function startDownload(id: number, size: number) {
  logState.downloading = true;
  logState.downloadId = id;
  logState.progress = 0;
  logState.downloadedBytes = 0;
  logState.downloadSpeed = '';
  logState._lastSpeedTime = 0;
  logState._lastSpeedBytes = 0;
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

export function completeDownload(id: number, b64data: string, size: number) {
  logState.downloading = false;
  logState.downloadId = -1;
  logState.progress = 100;
  logState.downloadSpeed = '';

  const raw = atob(b64data);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  const blob = new Blob([bytes], { type: 'application/octet-stream' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `log_${id}.bin`;
  a.click();
  URL.revokeObjectURL(url);
}

export function cancelDownload() {
  logState.downloading = false;
  logState.downloadId = -1;
  logState.progress = 0;
  logState.downloadSpeed = '';
}
