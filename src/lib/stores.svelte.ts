import type { DroneState, DroneEvent, Waypoint, Toast } from './types';
import { defaultState } from './types';

class AppState {
  drone: DroneState = $state({ ...defaultState });
  events: DroneEvent[] = $state([]);
  wsConnected: boolean = $state(false);
  waypoints: Waypoint[] = $state([]);
  undoStack: Waypoint[][] = $state([]);
  defaultAlt: number = $state(30);
  geoRadius: number = $state(500);
  darkTheme: boolean = $state(true);
  audioMuted: boolean = $state(false);
  voiceEnabled: boolean = $state(false);
  chartsOpen: boolean = $state(false);
  mapExpanded: boolean = $state(false);
  summaryShown: boolean = $state(false);
  toasts: Toast[] = $state([]);
  guidedMode: boolean = $state(false);
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
}

export function deleteWaypoint(i: number) {
  pushUndo();
  app.waypoints.splice(i, 1);
}

export function clearWaypoints() {
  pushUndo();
  app.waypoints = [];
}

export function loadSettings() {
  try {
    const s = JSON.parse(localStorage.getItem('pllink_v3_settings') || '{}');
    if (s.alt) app.defaultAlt = s.alt;
    if (s.radius) app.geoRadius = s.radius;
    if (s.dark !== undefined) app.darkTheme = s.dark;
    if (s.muted !== undefined) app.audioMuted = s.muted;
  } catch {}
}

export function saveSettings() {
  try {
    localStorage.setItem('pllink_v3_settings', JSON.stringify({
      alt: app.defaultAlt,
      radius: app.geoRadius,
      dark: app.darkTheme,
      muted: app.audioMuted,
    }));
  } catch {}
}

let _toastId = 0;
export function addToast(text: string, level: 'info' | 'warn' | 'error' | 'success' = 'info', duration = 4000) {
  const id = ++_toastId;
  app.toasts.push({ id, text, level });
  if (app.toasts.length > 5) app.toasts.shift();
  setTimeout(() => {
    const idx = app.toasts.findIndex(t => t.id === id);
    if (idx >= 0) app.toasts.splice(idx, 1);
  }, duration);
}

export function dismissToast(id: number) {
  const idx = app.toasts.findIndex(t => t.id === id);
  if (idx >= 0) app.toasts.splice(idx, 1);
}
