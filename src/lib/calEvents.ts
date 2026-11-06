// What the calibration panel counts as part of a run. A compass run is known by its event
// type, because on WebSerial its text comes in the UI language, which no pattern here knows.
export const CAL_TEXT =
  /校准|calibrat|cal |gyro|compass|accel|baro|level|place|rotate|orientation|complete|success|完成|成功|失败|failed|progress/i;

export function isCalEvent(ev: { text: string; event_type?: string }): boolean {
  return ev.event_type === 'cal_compass' || CAL_TEXT.test(ev.text);
}
