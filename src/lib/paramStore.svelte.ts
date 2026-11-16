import type { Param } from './types';

export const PARAM_STORE_MAX = 2000;

class ParamState {
  list: Param[] = $state([]);
  total: number = $state(0);
  received: number = $state(0);
  fetching: boolean = $state(false);
}

export const paramState = new ParamState();

const nameIndex = new Map<string, number>();
let lastFetchGen: number | undefined;

export function handleParamBatch(
  params: {
    name: string;
    value: number;
    ptype: number;
    index: number;
    total: number;
    received: number;
    fetching?: boolean;
    fetch_gen?: number;
    /** True only for the reply to our own PARAM_SET for a name not read yet. */
    allow_new?: boolean;
  }[],
) {
  const generation = params.find((p) => p.fetch_gen !== undefined)?.fetch_gen;
  if (generation !== undefined && generation !== lastFetchGen) {
    // Another tab may have started this fetch. Its Read All cannot clear our storage directly,
    // but the generation on the broadcast replaces a capped or stale list here too.
    clearParams();
    lastFetchGen = generation;
  }
  const arr = paramState.list.slice();
  let capped = false;
  for (const p of params) {
    const param: Param = { name: p.name, value: p.value, type: p.ptype, index: p.index };
    const idx = nameIndex.get(p.name);
    if (idx !== undefined) {
      arr[idx] = param;
      continue;
    }
    // Missing fetching is the legacy shape of a fetch batch. An explicit false outside one
    // accepts no new name unless the backend marked this as our own PARAM_SET echo.
    const active = p.fetching ?? true;
    if (!active && p.allow_new !== true) continue;
    if (arr.length >= PARAM_STORE_MAX) {
      capped = true;
      continue;
    }
    nameIndex.set(p.name, arr.length);
    arr.push(param);
  }
  paramState.list = arr;
  if (capped) {
    paramState.fetching = false;
  } else if (params.length > 0) {
    const last = params[params.length - 1];
    paramState.total = last.total;
    paramState.received = last.received;
    // The backend says whether a fetch is running. A value the FC sent on its
    // own is 1 of 1028 with nothing to finish it, so the counters would latch
    // this true for good. The serial path only calls this inside a fetch.
    paramState.fetching = last.fetching ?? last.received < last.total;
  }
}

export function handleParamsComplete() {
  paramState.fetching = false;
  const sorted = paramState.list.slice().sort((a, b) => a.name.localeCompare(b.name));
  nameIndex.clear();
  for (let i = 0; i < sorted.length; i++) {
    nameIndex.set(sorted[i].name, i);
  }
  paramState.list = sorted;
}

export function handleParamTimeout() {
  paramState.fetching = false;
}

/** Upsert one row WITHOUT touching total/received/fetching — for PARAM_SET
 * echoes and unsolicited values outside a fetch. Routing an echo through
 * handleParamBatch would replay stale fetch counters: after a timed-out
 * partial fetch (say 300/1000) the recomputed `fetching = received < total`
 * re-latches true with no ticker running, permanently disabling the
 * Read-All button until reconnect. */
export function updateParamRow(name: string, value: number, ptype: number, index: number, allowNew = false) {
  const arr = paramState.list.slice();
  const param: Param = { name, value, type: ptype, index };
  const idx = nameIndex.get(name);
  if (idx !== undefined) {
    arr[idx] = param;
  } else {
    if (!allowNew || arr.length >= PARAM_STORE_MAX) return;
    nameIndex.set(name, arr.length);
    arr.push(param);
  }
  paramState.list = arr;
}

/** Serial-path fetch kickoff: clear stale values and show progress
 * immediately, mirroring backend request_all() (params.clear() +
 * fetching=True before the first PARAM_VALUE arrives). The ws path never
 * calls this — the backend owns that lifecycle and pushes param_batch. */
export function startParamFetch() {
  clearParams();
  paramState.fetching = true;
}

export function hasParam(name: string): boolean {
  return nameIndex.has(name);
}

export function getParam(name: string, fallback: number): number {
  // The list is read first and always: nameIndex is no state, so a $derived that only
  // looked it up would never hear of a name arriving after the panel opened.
  const list = paramState.list;
  const idx = nameIndex.get(name);
  return idx !== undefined ? list[idx].value : fallback;
}

export function clearParams() {
  paramState.list = [];
  paramState.total = 0;
  paramState.received = 0;
  paramState.fetching = false;
  nameIndex.clear();
  lastFetchGen = undefined;
}
