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

  it('leaves out the ack of a command that is no calibration', () => {
    // What a mode change during a calibration puts in the event list, on both links.
    expect(isCalEvent({ text: 'Command: Mode — success', event_type: 'cmd_ack_ok' })).toBe(false);
    expect(isCalEvent({ text: '指令应答: 模式 — 成功', event_type: 'cmd_ack_ok' })).toBe(false);
    expect(isCalEvent({ text: 'Command: Arm/Disarm — failed', event_type: 'cmd_ack_fail' })).toBe(false);
    expect(isCalEvent({ text: '指令应答: 解锁/锁定 — 失败', event_type: 'cmd_ack_fail' })).toBe(false);
  });

  it('keeps the ack of a calibration command', () => {
    expect(isCalEvent({ text: 'Command: Calibration — failed', event_type: 'cmd_ack_fail' })).toBe(true);
    expect(isCalEvent({ text: '指令应答: 罗盘校准 — 拒绝', event_type: 'cmd_ack_fail' })).toBe(true);
    expect(isCalEvent({ text: 'Command: Cancel Compass Cal — success', event_type: 'cmd_ack_ok' })).toBe(true);
  });

  it('reads the whole text of anything that is not an ack', () => {
    expect(isCalEvent({ text: 'Calibration successful', event_type: 'statustext' })).toBe(true);
    expect(isCalEvent({ text: 'Place vehicle level — and press any key', event_type: 'statustext' })).toBe(true);
  });
});
