import { describe, expect, it } from 'vitest';
import { offlineDownloadOutcome } from './offlineDownload';

describe('offline tile download results', () => {
  it('treats a fully cached region as success', () => {
    expect(offlineDownloadOutcome({ total: 12, downloaded: 0, skipped: 12, truncated: false })).toBe('done');
  });

  it('reports partial coverage and truncation as incomplete', () => {
    expect(offlineDownloadOutcome({ total: 2, downloaded: 0, skipped: 1, truncated: false })).toBe('incomplete');
    expect(offlineDownloadOutcome({ total: 12, downloaded: 0, skipped: 0, truncated: true })).toBe('incomplete');
    expect(offlineDownloadOutcome({ total: 15, downloaded: 3, skipped: 12, truncated: true })).toBe('incomplete');
  });

  it('distinguishes an empty request from a complete download', () => {
    expect(offlineDownloadOutcome({ total: 0, downloaded: 0, skipped: 0, truncated: false })).toBe('none');
    expect(offlineDownloadOutcome({ total: 15, downloaded: 3, skipped: 12, truncated: false })).toBe('done');
  });
});
