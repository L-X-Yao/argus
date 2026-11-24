export interface OfflineDownloadResult {
  total: number;
  downloaded: number;
  skipped: number;
  truncated?: boolean;
}

export type OfflineDownloadOutcome = 'done' | 'incomplete' | 'none';

export function offlineDownloadOutcome(data: OfflineDownloadResult): OfflineDownloadOutcome {
  if (data.total === 0 && data.downloaded === 0 && data.skipped === 0) return 'none';
  if (data.truncated) return 'incomplete';
  // Cached tiles count as coverage; a partial cache hit is not a completed region.
  return data.downloaded + data.skipped >= data.total ? 'done' : 'incomplete';
}
