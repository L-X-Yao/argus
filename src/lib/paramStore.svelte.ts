import type { Param } from './types';

class ParamState {
  list: Param[] = $state([]);
  total: number = $state(0);
  received: number = $state(0);
  fetching: boolean = $state(false);
}

export const paramState = new ParamState();

const nameIndex = new Map<string, number>();

export function handleParamBatch(params: { name: string; value: number; ptype: number; index: number; total: number; received: number }[]) {
  const arr = paramState.list.slice();
  for (const p of params) {
    const param: Param = { name: p.name, value: p.value, type: p.ptype, index: p.index };
    const idx = nameIndex.get(p.name);
    if (idx !== undefined) {
      arr[idx] = param;
    } else {
      nameIndex.set(p.name, arr.length);
      arr.push(param);
    }
  }
  paramState.list = arr;
  if (params.length > 0) {
    const last = params[params.length - 1];
    paramState.total = last.total;
    paramState.received = last.received;
    paramState.fetching = last.received < last.total;
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

export function updateSingleParam(name: string, value: number) {
  const idx = nameIndex.get(name);
  if (idx !== undefined) {
    paramState.list[idx] = { ...paramState.list[idx], value };
  }
}

export function clearParams() {
  paramState.list = [];
  paramState.total = 0;
  paramState.received = 0;
  paramState.fetching = false;
  nameIndex.clear();
}
