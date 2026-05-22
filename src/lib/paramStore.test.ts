import { describe, it, expect, beforeEach } from 'vitest';
import { paramState, handleParamBatch, handleParamsComplete, updateSingleParam, clearParams } from './paramStore.svelte';

beforeEach(() => {
  clearParams();
});

describe('handleParamBatch', () => {
  it('adds params to list', () => {
    handleParamBatch([
      { name: 'ANGLE_MAX', value: 3000, ptype: 9, index: 0, total: 2, received: 1 },
      { name: 'BATT_ARM_VOLT', value: 10.5, ptype: 9, index: 1, total: 2, received: 2 },
    ]);
    expect(paramState.list.length).toBe(2);
    expect(paramState.list[0].name).toBe('ANGLE_MAX');
    expect(paramState.total).toBe(2);
  });

  it('updates existing param by name', () => {
    handleParamBatch([{ name: 'X', value: 1, ptype: 9, index: 0, total: 1, received: 1 }]);
    handleParamBatch([{ name: 'X', value: 2, ptype: 9, index: 0, total: 1, received: 1 }]);
    expect(paramState.list.length).toBe(1);
    expect(paramState.list[0].value).toBe(2);
  });

  it('sets fetching true when incomplete', () => {
    handleParamBatch([{ name: 'A', value: 0, ptype: 9, index: 0, total: 10, received: 1 }]);
    expect(paramState.fetching).toBe(true);
  });
});

describe('handleParamsComplete', () => {
  it('sets fetching false and sorts', () => {
    handleParamBatch([
      { name: 'Z_PARAM', value: 0, ptype: 9, index: 0, total: 2, received: 1 },
      { name: 'A_PARAM', value: 0, ptype: 9, index: 1, total: 2, received: 2 },
    ]);
    handleParamsComplete();
    expect(paramState.fetching).toBe(false);
    expect(paramState.list[0].name).toBe('A_PARAM');
    expect(paramState.list[1].name).toBe('Z_PARAM');
  });
});

describe('updateSingleParam', () => {
  it('updates value by name', () => {
    handleParamBatch([{ name: 'TEST', value: 100, ptype: 9, index: 0, total: 1, received: 1 }]);
    updateSingleParam('TEST', 200);
    expect(paramState.list[0].value).toBe(200);
  });

  it('ignores unknown param', () => {
    updateSingleParam('NONEXISTENT', 999);
    expect(paramState.list.length).toBe(0);
  });
});

describe('clearParams', () => {
  it('resets all state', () => {
    handleParamBatch([{ name: 'X', value: 1, ptype: 9, index: 0, total: 1, received: 1 }]);
    clearParams();
    expect(paramState.list.length).toBe(0);
    expect(paramState.total).toBe(0);
    expect(paramState.fetching).toBe(false);
  });
});
