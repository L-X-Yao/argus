import { describe, expect, it } from 'vitest';
import { offlineDownloadOutcome } from './offlineDownload';

describe('offline tile download results', () => {
  it('treats a fully cached region as success', () => {
    expect(offlineDownloadOutcome({ downloaded: 0, skipped: 12, truncated: false })).toBe('done');
  });

  it('keeps an empty result and a truncated result distinct', () => {
    expect(offlineDownloadOutcome({ downloaded: 0, skipped: 0, truncated: false })).toBe('none');
    expect(offlineDownloadOutcome({ downloaded: 0, skipped: 12, truncated: true })).toBe('incomplete');
    expect(offlineDownloadOutcome({ downloaded: 3, skipped: 12, truncated: true })).toBe('incomplete');
  });
});
