import { describe, it, expect, vi } from 'vitest';

const H = vi.hoisted(() => ({ drone: { vtype_raw: 0, vtol_state: 0 }, plane: false }));
vi.mock('./stores.svelte', () => ({ app: { drone: H.drone }, isPlane: () => H.plane }));

import { specialModes, vehicleKind } from './vehicleModes';

const on = (vtypeRaw: number, plane = false, vtolState = 0) => {
  H.drone.vtype_raw = vtypeRaw;
  H.drone.vtol_state = vtolState;
  H.plane = plane;
};

describe('vehicle modes', () => {
  it.each([
    ['quad', 2, false, 'copter', { hold: 5, land: 9, autotune: 15 }],
    ['fixed wing', 1, true, 'plane', { hold: 12, land: null, autotune: 8 }],
    ['QuadPlane', 20, true, 'plane', { hold: 19, land: 20, autotune: 8 }],
    ['rover', 10, false, 'rover', { hold: 4, land: null, autotune: null }],
    ['boat', 11, false, 'rover', { hold: 4, land: null, autotune: null }],
    ['sub', 12, false, 'sub', { hold: 16, land: 9, autotune: null }],
  ])('%s', (_, vtypeRaw, plane, kind, modes) => {
    on(vtypeRaw, plane);
    expect(vehicleKind()).toBe(kind);
    expect(specialModes()).toMatchObject(modes);
  });

  it('a default QuadPlane heartbeats as a fixed wing and still gets the VTOL modes', () => {
    on(1, true, 3);
    expect(specialModes()).toMatchObject({ hold: 19, land: 20 });
  });

  it('a Copter always reports MC, which makes it nothing but a Copter', () => {
    on(2, false, 3);
    expect(specialModes()).toMatchObject({ hold: 5, land: 9 });
  });
});
