import { describe, it, expect } from 'vitest';
import { detectAdapter, ardupilotAdapter, px4Adapter } from './index';

describe('FC adapter detection', () => {
  it('detects ArduPilot from autopilot=3', () => {
    const a = detectAdapter(3);
    expect(a.type).toBe('ardupilot');
  });

  it('detects PX4 from autopilot=12', () => {
    const a = detectAdapter(12);
    expect(a.type).toBe('px4');
  });

  it('defaults to ArduPilot for unknown autopilot', () => {
    expect(detectAdapter(99).type).toBe('ardupilot');
  });
});

describe('ArduPilot adapter', () => {
  it('resolves copter mode names', () => {
    expect(ardupilotAdapter.modeName(0, false)).toBe('Stabilize');
    expect(ardupilotAdapter.modeName(5, false)).toBe('Loiter');
    expect(ardupilotAdapter.modeName(6, false)).toBe('RTL');
  });

  it('resolves plane mode names', () => {
    expect(ardupilotAdapter.modeName(0, true)).toBe('Manual');
    expect(ardupilotAdapter.modeName(10, true)).toBe('Auto');
    expect(ardupilotAdapter.modeName(11, true)).toBe('RTL');
  });

  it('returns mode buttons', () => {
    const btns = ardupilotAdapter.modeButtons(false);
    expect(btns.length).toBeGreaterThan(0);
    expect(btns[0]).toEqual([2, 'AltHold']);
  });

  it('allModes returns FlightMode objects', () => {
    const modes = ardupilotAdapter.allModes(false);
    expect(modes.length).toBeGreaterThan(10);
    const rtl = modes.find(m => m.name === 'RTL');
    expect(rtl?.category).toBe('emergency');
  });

  it('RTL mode IDs', () => {
    expect(ardupilotAdapter.rtlModeId(false)).toBe(6);
    expect(ardupilotAdapter.rtlModeId(true)).toBe(11);
  });
});

describe('PX4 adapter', () => {
  it('resolves PX4 mode names', () => {
    const posctl = (3 << 16); // main=3 (POSCTL)
    expect(px4Adapter.modeName(posctl, false)).toBe('Position');
  });

  it('resolves PX4 auto sub-modes', () => {
    const mission = (4 << 24) | (4 << 16); // sub=4 (MISSION), main=4 (AUTO)
    expect(px4Adapter.modeName(mission, false)).toBe('Mission');
  });

  it('returns mode buttons', () => {
    const btns = px4Adapter.modeButtons(false);
    expect(btns.length).toBeGreaterThan(0);
  });

  it('allModes includes Return mode as emergency', () => {
    const modes = px4Adapter.allModes(false);
    const rtl = modes.find(m => m.name === 'Return');
    expect(rtl).toBeDefined();
    expect(rtl?.category).toBe('emergency');
  });
});
