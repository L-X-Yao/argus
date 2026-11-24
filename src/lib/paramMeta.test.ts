import { describe, expect, it } from 'vitest';
import { metadataWriteAllowed, shouldFetchMeta } from './paramMeta';

const A = 'copter|zh|4.6.3|4.6.3';
const B = 'copter|zh|4.5.7|4.5.7';

describe('parameter metadata request lifecycle', () => {
  it('refuses metadata-driven writes while another series is loading or after it failed', () => {
    expect(metadataWriteAllowed(A, A, false)).toBe(true);
    expect(metadataWriteAllowed(A, B, true)).toBe(false);
    expect(metadataWriteAllowed(A, B, false)).toBe(false);
    expect(metadataWriteAllowed(B, B, false)).toBe(true);
  });

  it('retries a failed key only after the next Read All completes, not in a tight loop', () => {
    expect(shouldFetchMeta({ key: B, lastKey: B, failedKey: B, fetching: false, inFlight: true })).toBe(false);
    expect(shouldFetchMeta({ key: B, lastKey: B, failedKey: B, fetching: true, inFlight: false })).toBe(false);
    expect(shouldFetchMeta({ key: B, lastKey: B, failedKey: B, fetching: false, inFlight: false })).toBe(true);
    expect(shouldFetchMeta({ key: B, lastKey: B, failedKey: '', fetching: false, inFlight: false })).toBe(false);
    expect(shouldFetchMeta({ key: A, lastKey: B, failedKey: B, fetching: false, inFlight: false })).toBe(true);
  });
});
