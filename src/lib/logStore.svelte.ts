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
}

export const logState = new LogState();

export function setLogList(logs: LogEntry[]) {
  logState.list = logs;
}

export function startDownload(id: number, size: number) {
  logState.downloading = true;
  logState.downloadId = id;
  logState.progress = 0;
}

export function completeDownload(id: number, b64data: string, size: number) {
  logState.downloading = false;
  logState.downloadId = -1;
  logState.progress = 100;

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
}
