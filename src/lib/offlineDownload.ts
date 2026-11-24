export interface OfflineDownloadResult {
  downloaded: number;
  skipped: number;
  truncated?: boolean;
}

export type OfflineDownloadOutcome = 'done' | 'incomplete' | 'none';

export function offlineDownloadOutcome(data: OfflineDownloadResult): OfflineDownloadOutcome {
  // Cached tiles are a successful offline result too, even when nothing new was fetched.
  if (data.downloaded === 0 && data.skipped === 0) return 'none';
  if (data.truncated) return 'incomplete';
  return 'done';
}
