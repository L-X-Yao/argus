import { describe, it, expect, afterEach } from 'vitest';
import { flushSync } from 'svelte';
import { clearParams, getParam, handleParamBatch } from './paramStore.svelte';

afterEach(() => clearParams());

describe('getParam in a $derived', () => {
  it('wakes up when the name arrives after the panel opened', () => {
    const cleanup = $effect.root(() => {
      const mult = $derived(getParam('BATT_VOLT_MULT', 0));
      let seen = -1;
      $effect(() => {
        seen = mult;
      });
      flushSync();
      expect(seen).toBe(0);

      handleParamBatch([{ name: 'BATT_VOLT_MULT', value: 10.1, ptype: 9, index: 0, total: 1, received: 1 }]);
      flushSync();
      expect(seen).toBe(10.1);
    });
    cleanup();
  });
});
