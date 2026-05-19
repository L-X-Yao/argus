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
  for (const p of params) {
    const param: Param = { name: p.name, value: p.value, type: p.ptype, index: p.index };
    const idx = nameIndex.get(p.name);
    if (idx !== undefined) {
      paramState.list[idx] = param;
    } else {
      nameIndex.set(p.name, paramState.list.length);
      paramState.list.push(param);
    }
  }
  if (params.length > 0) {
    const last = params[params.length - 1];
    paramState.total = last.total;
    paramState.received = last.received;
    paramState.fetching = last.received < last.total;
  }
}

export function handleParamsComplete() {
  paramState.fetching = false;
  paramState.list.sort((a, b) => a.name.localeCompare(b.name));
  nameIndex.clear();
  for (let i = 0; i < paramState.list.length; i++) {
    nameIndex.set(paramState.list[i].name, i);
  }
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
