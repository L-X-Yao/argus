import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock dependencies before importing module
vi.mock('./ws', () => ({ sendCommand: vi.fn() }));
vi.mock('./stores.svelte', () => ({
  app: { drone: { connected: false, armed: false } },
}));

import { gamepad, loadGamepadMap, saveGamepadMap, startGamepad, stopGamepad } from './gamepad.svelte';

function makeStorage(): Storage {
  const store = new Map<string, string>();
  return {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => { store.set(k, v); },
    removeItem: (k: string) => { store.delete(k); },
    clear: () => store.clear(),
    get length() { return store.size; },
    key: (i: number) => [...store.keys()][i] ?? null,
  };
}

beforeEach(() => {
  vi.stubGlobal('localStorage', makeStorage());
  vi.stubGlobal('window', {
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
  vi.stubGlobal('requestAnimationFrame', vi.fn());
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  vi.stubGlobal('navigator', { getGamepads: vi.fn(() => []) });
  // Reset gamepad state
  gamepad.connected = false;
  gamepad.name = '';
  gamepad.axes = [0, 0, 0, 0];
  gamepad.buttons = [];
  gamepad.enabled = false;
  gamepad.deadzone = 0.08;
  gamepad.channelMap = {
    roll: 0, pitch: 1, throttle: 3, yaw: 2,
    invertRoll: false, invertPitch: true, invertThrottle: true, invertYaw: false,
  };
});

describe('gamepad default state', () => {
  it('has sensible defaults', () => {
    expect(gamepad.connected).toBe(false);
    expect(gamepad.enabled).toBe(false);
    expect(gamepad.deadzone).toBe(0.08);
    expect(gamepad.axes).toEqual([0, 0, 0, 0]);
  });

  it('has default channel map', () => {
    expect(gamepad.channelMap.roll).toBe(0);
    expect(gamepad.channelMap.pitch).toBe(1);
    expect(gamepad.channelMap.yaw).toBe(2);
    expect(gamepad.channelMap.throttle).toBe(3);
    expect(gamepad.channelMap.invertPitch).toBe(true);
    expect(gamepad.channelMap.invertThrottle).toBe(true);
    expect(gamepad.channelMap.invertRoll).toBe(false);
    expect(gamepad.channelMap.invertYaw).toBe(false);
  });
});

describe('loadGamepadMap', () => {
  it('loads saved channel map from localStorage', () => {
    const custom = {
      roll: 1, pitch: 0, throttle: 2, yaw: 3,
      invertRoll: true, invertPitch: false, invertThrottle: false, invertYaw: true,
    };
    localStorage.setItem('argus_gamepad_map', JSON.stringify(custom));
    loadGamepadMap();
    expect(gamepad.channelMap.roll).toBe(1);
    expect(gamepad.channelMap.pitch).toBe(0);
    expect(gamepad.channelMap.invertRoll).toBe(true);
    expect(gamepad.channelMap.invertYaw).toBe(true);
  });

  it('keeps defaults when localStorage is empty', () => {
    loadGamepadMap();
    expect(gamepad.channelMap.roll).toBe(0);
    expect(gamepad.channelMap.pitch).toBe(1);
  });

  it('handles corrupted JSON gracefully', () => {
    localStorage.setItem('argus_gamepad_map', '{broken');
    loadGamepadMap();
    // Should not crash; defaults remain
    expect(gamepad.channelMap.roll).toBe(0);
  });

  it('merges partial saved config with defaults', () => {
    localStorage.setItem('argus_gamepad_map', JSON.stringify({ roll: 3 }));
    loadGamepadMap();
    expect(gamepad.channelMap.roll).toBe(3);
    expect(gamepad.channelMap.pitch).toBe(1); // default preserved
  });

  it('ignores saved config without roll key', () => {
    localStorage.setItem('argus_gamepad_map', JSON.stringify({ customField: 'test' }));
    loadGamepadMap();
    expect(gamepad.channelMap.roll).toBe(0); // default preserved
  });
});

describe('saveGamepadMap', () => {
  it('persists current channel map to localStorage', () => {
    gamepad.channelMap.roll = 2;
    gamepad.channelMap.invertYaw = true;
    saveGamepadMap();
    const saved = JSON.parse(localStorage.getItem('argus_gamepad_map')!);
    expect(saved.roll).toBe(2);
    expect(saved.invertYaw).toBe(true);
  });

  it('roundtrips through save and load', () => {
    gamepad.channelMap = {
      roll: 3, pitch: 2, throttle: 1, yaw: 0,
      invertRoll: true, invertPitch: false, invertThrottle: false, invertYaw: true,
    };
    saveGamepadMap();
    // Reset to defaults
    gamepad.channelMap = {
      roll: 0, pitch: 1, throttle: 3, yaw: 2,
      invertRoll: false, invertPitch: true, invertThrottle: true, invertYaw: false,
    };
    loadGamepadMap();
    expect(gamepad.channelMap.roll).toBe(3);
    expect(gamepad.channelMap.yaw).toBe(0);
    expect(gamepad.channelMap.invertRoll).toBe(true);
  });
});

describe('startGamepad / stopGamepad', () => {
  it('startGamepad enables and registers listeners', () => {
    startGamepad();
    expect(gamepad.enabled).toBe(true);
    expect(window.addEventListener).toHaveBeenCalledWith('gamepadconnected', expect.any(Function));
    expect(window.addEventListener).toHaveBeenCalledWith('gamepaddisconnected', expect.any(Function));
  });

  it('stopGamepad disables and removes listeners', () => {
    startGamepad();
    stopGamepad();
    expect(gamepad.enabled).toBe(false);
    expect(gamepad.connected).toBe(false);
    expect(window.removeEventListener).toHaveBeenCalledWith('gamepadconnected', expect.any(Function));
    expect(window.removeEventListener).toHaveBeenCalledWith('gamepaddisconnected', expect.any(Function));
  });
});
