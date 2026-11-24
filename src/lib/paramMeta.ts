export interface MetaRetryState {
  key: string;
  lastKey: string;
  failedKey: string;
  fetching: boolean;
  inFlight: boolean;
}

/** A new key starts at once; a failed key retries only after another Read All completes. */
export function shouldFetchMeta({ key, lastKey, failedKey, fetching, inFlight }: MetaRetryState): boolean {
  if (key !== lastKey) return true;
  return failedKey === key && !fetching && !inFlight;
}

/** Metadata captured under another vehicle/series/locale key cannot drive a write. */
export function metadataWriteAllowed(appliedKey: string, requestedKey: string, loading: boolean): boolean {
  return appliedKey !== '' && appliedKey === requestedKey && !loading;
}
