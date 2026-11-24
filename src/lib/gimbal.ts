import type { DroneEvent } from './types';

export interface RecordingVehicle {
  sysid: number;
  connected: boolean;
}

/** Camera ACKs belong to this mount and this vehicle/link generation only. */
export class CameraRecordingTracker {
  private mark: DroneEvent | undefined;
  private sysid: number;
  private connected: boolean;
  private recording = false;

  constructor(events: DroneEvent[], vehicle: RecordingVehicle) {
    this.mark = events[events.length - 1];
    this.sysid = vehicle.sysid;
    this.connected = vehicle.connected;
  }

  sync(events: DroneEvent[], vehicle: RecordingVehicle): boolean {
    if (vehicle.sysid !== this.sysid || vehicle.connected !== this.connected) {
      this.sysid = vehicle.sysid;
      this.connected = vehicle.connected;
      this.recording = false;
      this.mark = events[events.length - 1];
      return false;
    }

    const markIndex = this.mark ? events.lastIndexOf(this.mark) : -1;
    // If the marker was trimmed, every retained event is newer than it.
    const start = markIndex >= 0 ? markIndex + 1 : 0;
    for (let i = start; i < events.length; i++) {
      const ev = events[i];
      if (ev.event_type !== 'cmd_ack_ok') continue;
      if (ev.cmd === 2500) this.recording = true;
      else if (ev.cmd === 2501) this.recording = false;
    }
    if (events.length > 0) this.mark = events[events.length - 1];
    return this.recording;
  }
}
