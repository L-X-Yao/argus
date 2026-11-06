import { describe, it, expect } from 'vitest';
import { isCalEvent } from './calEvents';

describe('calibration events', () => {
  it('knows a compass event in any language by its type', () => {
    expect(isCalEvent({ text: 'Kompass kalibriert', event_type: 'cal_compass' })).toBe(true);
  });

  it('still reads the text of the other calibrations', () => {
    expect(isCalEvent({ text: 'Gyro calibration started', event_type: 'statustext' })).toBe(true);
  });

  it('leaves everything else out', () => {
    expect(isCalEvent({ text: 'Mode changed', event_type: 'statustext' })).toBe(false);
  });
});
