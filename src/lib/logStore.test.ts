import { describe, it, expect } from 'vitest';
import { logState, setLogList, startDownload, updateDownloadProgress, cancelDownload } from './logStore.svelte';

describe('logStore', () => {
  it('setLogList replaces list', () => {
    setLogList([{ id: 1, size: 1024, time_utc: 1000 }]);
    expect(logState.list.length).toBe(1);
    expect(logState.list[0].id).toBe(1);
    setLogList([]);
    expect(logState.list.length).toBe(0);
  });

  it('startDownload sets state', () => {
    startDownload(5, 2048);
    expect(logState.downloading).toBe(true);
    expect(logState.downloadId).toBe(5);
    expect(logState.progress).toBe(0);
  });

  it('updateDownloadProgress calculates percentage', () => {
    startDownload(1, 1000);
    updateDownloadProgress(500, 1000);
    expect(logState.progress).toBe(50);
  });

  it('cancelDownload resets state', () => {
    startDownload(1, 1000);
    cancelDownload();
    expect(logState.downloading).toBe(false);
    expect(logState.downloadId).toBe(-1);
    expect(logState.progress).toBe(0);
  });
});
