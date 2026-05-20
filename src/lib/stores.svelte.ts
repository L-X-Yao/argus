import type { DroneState, DroneEvent, Waypoint, Toast } from './types';
import { defaultState } from './types';

class AppState {
  drone: DroneState = $state({ ...defaultState });
  events: DroneEvent[] = $state([]);
  wsConnected: boolean = $state(false);
  waypoints: Waypoint[] = $state([]);
  undoStack: Waypoint[][] = $state([]);
  defaultAlt: number = $state(30);
  defaultSpeed: number = $state(5);
  geoRadius: number = $state(500);
  darkTheme: boolean = $state(true);
  audioMuted: boolean = $state(false);
  voiceEnabled: boolean = $state(false);
  chartsOpen: boolean = $state(false);
  mapExpanded: boolean = $state(false);
  summaryShown: boolean = $state(false);
  toasts: Toast[] = $state([]);
  guidedMode: boolean = $state(false);
  focusWp: number = $state(-1);
  replayPos: { lat: number; lon: number; yaw: number } | null = $state(null);
  surveyPolygon: { lat: number; lon: number }[] = $state([]);
  drawingPolygon: boolean = $state(false);
  showSurvey: boolean = $state(false);
  fencePolygon: { lat: number; lon: number }[] = $state([]);
  drawingFence: boolean = $state(false);
  showFence: boolean = $state(false);
  fenceUploaded: boolean = $state(false);
  showParams: boolean = $state(false);
  showRc: boolean = $state(false);
  showVibe: boolean = $state(false);
  showServo: boolean = $state(false);
  showSettings: boolean = $state(false);
}

export const app = new AppState();

export function updateState(s: DroneState) {
  Object.assign(app.drone, s);
}

export function setWsConnected(v: boolean) {
  app.wsConnected = v;
}

export function addEvent(ev: DroneEvent) {
  app.events.push(ev);
  if (app.events.length > 200) {
    app.events.splice(0, app.events.length - 100);
  }
}

export function clearEvents() {
  app.events.length = 0;
}

export function pushUndo() {
  app.undoStack.push(JSON.parse(JSON.stringify(app.waypoints)));
  if (app.undoStack.length > 20) app.undoStack.shift();
}

export function undo() {
  if (!app.undoStack.length) return;
  app.waypoints = app.undoStack.pop()!;
}

export function addWaypoint(wp: Waypoint) {
  pushUndo();
  app.waypoints.push(wp);
  saveWaypoints();
}

export function deleteWaypoint(i: number) {
  pushUndo();
  app.waypoints.splice(i, 1);
  saveWaypoints();
}

export function clearWaypoints() {
  pushUndo();
  app.waypoints = [];
  saveWaypoints();
}

export function loadSettings() {
  try {
    const s = JSON.parse(localStorage.getItem('pllink_v3_settings') || '{}');
    if (s.alt) app.defaultAlt = s.alt;
    if (s.speed) app.defaultSpeed = s.speed;
    if (s.radius) app.geoRadius = s.radius;
    if (s.dark !== undefined) app.darkTheme = s.dark;
    if (s.muted !== undefined) app.audioMuted = s.muted;
    if (s.voice !== undefined) app.voiceEnabled = s.voice;
  } catch {}
  try {
    const wps = JSON.parse(localStorage.getItem('pllink_v3_waypoints') || '[]');
    if (Array.isArray(wps) && wps.length > 0) app.waypoints = wps;
  } catch {}
}

export function saveSettings() {
  try {
    localStorage.setItem('pllink_v3_settings', JSON.stringify({
      alt: app.defaultAlt,
      speed: app.defaultSpeed,
      radius: app.geoRadius,
      dark: app.darkTheme,
      muted: app.audioMuted,
      voice: app.voiceEnabled,
    }));
  } catch {}
}

export function saveWaypoints() {
  try {
    localStorage.setItem('pllink_v3_waypoints', JSON.stringify(app.waypoints));
  } catch {}
}

export function generateCircle(centerLat: number, centerLon: number, radius: number, count: number, alt: number) {
  pushUndo();
  const pts: Waypoint[] = [];
  for (let i = 0; i < count; i++) {
    const angle = (i / count) * 2 * Math.PI;
    const dlat = radius * Math.cos(angle) / 111320;
    const dlon = radius * Math.sin(angle) / (111320 * Math.cos(centerLat * Math.PI / 180));
    pts.push({ lat: centerLat + dlat, lon: centerLon + dlon, alt, drop: false, delay: 0, speed: 0, type: 'wp' as const, loiter_param: 0 });
  }
  app.waypoints = [...app.waypoints, ...pts];
  saveWaypoints();
}

export function loadDownloadedMission(wps: Waypoint[]) {
  pushUndo();
  app.waypoints = wps.map(w => ({
    lat: w.lat, lon: w.lon, alt: w.alt,
    drop: w.drop || false, delay: w.delay || 0, speed: w.speed || 0,
    type: w.type || 'wp', loiter_param: w.loiter_param || 0,
  }));
  saveWaypoints();
}

// Confirm dialog
class ConfirmState {
  visible: boolean = $state(false);
  message: string = $state('');
  danger: boolean = $state(false);
  _resolve: ((v: boolean) => void) | null = null;
}
export const confirmState = new ConfirmState();

export function showConfirm(message: string, danger = false): Promise<boolean> {
  cancelSlide();
  return new Promise(resolve => {
    confirmState.message = message;
    confirmState.danger = danger;
    confirmState.visible = true;
    confirmState._resolve = resolve;
  });
}

class SlideConfirmState {
  visible: boolean = $state(false);
  text: string = $state('');
  color: string = $state('orange');
  _onConfirm: (() => void) | null = null;
}
export const slideState = new SlideConfirmState();

export function showSlide(text: string, color: string, onConfirm: () => void) {
  resolveConfirm(false);
  slideState.text = text;
  slideState.color = color;
  slideState.visible = true;
  slideState._onConfirm = onConfirm;
}

export function completeSlide() {
  slideState.visible = false;
  const fn = slideState._onConfirm;
  slideState._onConfirm = null;
  fn?.();
}

export function cancelSlide() {
  slideState.visible = false;
  slideState._onConfirm = null;
}

export function resolveConfirm(result: boolean) {
  confirmState.visible = false;
  confirmState._resolve?.(result);
  confirmState._resolve = null;
}

let _toastId = 0;
let _toastTimers = new Map<number, ReturnType<typeof setTimeout>>();
export function addToast(text: string, level: 'info' | 'warn' | 'error' | 'success' = 'info', duration = 4000) {
  const existing = app.toasts.find(t => t.text === text && t.level === level);
  if (existing) {
    existing.count++;
    const prev = _toastTimers.get(existing.id);
    if (prev) clearTimeout(prev);
    _toastTimers.set(existing.id, setTimeout(() => {
      const idx = app.toasts.findIndex(t => t.id === existing.id);
      if (idx >= 0) app.toasts.splice(idx, 1);
      _toastTimers.delete(existing.id);
    }, duration));
    return;
  }
  const id = ++_toastId;
  app.toasts.push({ id, text, level, count: 1 });
  if (app.toasts.length > 5) app.toasts.shift();
  _toastTimers.set(id, setTimeout(() => {
    const idx = app.toasts.findIndex(t => t.id === id);
    if (idx >= 0) app.toasts.splice(idx, 1);
    _toastTimers.delete(id);
  }, duration));
}

export function dismissToast(id: number) {
  const idx = app.toasts.findIndex(t => t.id === id);
  if (idx >= 0) app.toasts.splice(idx, 1);
}
