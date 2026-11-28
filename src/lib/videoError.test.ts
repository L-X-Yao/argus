import { describe, expect, it } from 'vitest';
import { videoErrorKey } from './videoError';

describe('videoErrorKey', () => {
  it.each([
    ['refused', 'video.errRefused'],
    ['timeout', 'video.errTimeout'],
    ['auth', 'video.errAuth'],
    ['notfound', 'video.errNotFound'],
    ['unreachable', 'video.errUnreachable'],
    ['server', 'video.errServer'],
    ['protocol', 'video.errProtocol'],
  ])('maps %s', (code, key) => {
    expect(videoErrorKey(code)).toBe(key);
  });

  it('falls back to the generic message for anything else', () => {
    expect(videoErrorKey('other')).toBe('video.loadFail');
    expect(videoErrorKey('')).toBe('video.loadFail');
    expect(videoErrorKey(null)).toBe('video.loadFail');
    expect(videoErrorKey(undefined)).toBe('video.loadFail');
    expect(videoErrorKey('constructor')).toBe('video.loadFail');
  });
});
