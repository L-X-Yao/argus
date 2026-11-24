import { describe, expect, it } from 'vitest';
import { CameraRecordingTracker } from './gimbal';
import type { DroneEvent } from './types';

function ack(cmd: number): DroneEvent {
  return { type: 'event', time: '12:00:00', text: 'ack', event_type: 'cmd_ack_ok', cmd };
}

const vehicle = { sysid: 1, connected: true };

describe('camera recording ACK ownership', () => {
  it('ignores ACKs from before the mount and resets across reconnect and vehicle changes', () => {
    const oldStart = ack(2500);
    const events = [oldStart];
    const tracker = new CameraRecordingTracker(events, vehicle);
    expect(tracker.sync(events, vehicle)).toBe(false);

    const newStart = ack(2500);
    events.push(newStart);
    expect(tracker.sync(events, vehicle)).toBe(true);

    expect(tracker.sync(events, { sysid: 1, connected: false })).toBe(false);
    expect(tracker.sync(events, vehicle)).toBe(false);

    const startAfterReconnect = ack(2500);
    events.push(startAfterReconnect);
    expect(tracker.sync(events, vehicle)).toBe(true);
    expect(tracker.sync(events, { sysid: 2, connected: true })).toBe(false);

    const stop = ack(2501);
    events.push(stop);
    expect(tracker.sync(events, { sysid: 2, connected: true })).toBe(false);
  });

  it('accepts a post-mount ACK when the mount marker was trimmed', () => {
    const marker = { type: 'event', time: '12:00:01', text: 'other', event_type: 'info' } as DroneEvent;
    const tracker = new CameraRecordingTracker([marker], vehicle);
    expect(tracker.sync([ack(2500)], vehicle)).toBe(true);
  });
});
