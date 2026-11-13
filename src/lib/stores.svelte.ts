import type { DroneState, DroneEvent, FlightSummary, Waypoint, Toast, RallyPoint } from './types';
import { defaultState } from './types';
import { cleanPositions, cleanRallyPoints, cleanWaypoints, finiteNumber } from './missionIO';
import { t } from './i18n.svelte';

class AppState {
  drone: DroneState = $state({ ...defaultState });
  events: DroneEvent[] = $state([]);
  wsConnected: boolean = $state(false);
  // Which transport owns the FC link right now. 'ws' = via backend (TCP/UDP/
  // serial over the FastAPI proxy). 'serial' = via WebSerial directly in the
  // browser. Mutex: only one may write drone fields at a time; the button-
  // level gate in ConnectionForm refuses to start the inactive transport
  // until the active one disconnects. See known issue #16 in FEATURE_CHECKLIST.
  activeTransport: 'none' | 'ws' | 'serial' = $state('none');
  // The USB link dropped and the session has not ended: see updateState.
  serialLinkLost: boolean = $state(false);
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
  // The summary window clears drone.flight_summary when it closes, and the report comes after.
  lastFlight: FlightSummary | null = $state(null);
  toasts: Toast[] = $state([]);
  guidedMode: boolean = $state(false);
  focusWp: number = $state(-1);
  fitRouteFlag: number = $state(0);
  replayPos: { lat: number; lon: number; yaw: number } | null = $state(null);
  surveySpacing: number = $state(20);
  surveyPolygon: { lat: number; lon: number }[] = $state([]);
  drawingPolygon: boolean = $state(false);
  showSurvey: boolean = $state(false);
  fencePolygon: { lat: number; lon: number }[] = $state([]);
  drawingFence: boolean = $state(false);
  showFence: boolean = $state(false);
  fenceUploaded: boolean = $state(false);
  showSettings: boolean = $state(false);
  mapRegion: 'china' | 'global' = $state('china');
  tileSource: string = $state('amap');
  mapMode: '2d' | '3d' = $state('2d');
  linkHistory: { t: number; rate: number; age: number }[] = $state([]);
  rallyPoints: RallyPoint[] = $state([]);
  rallyUploaded: boolean = $state(false);
  showRally: boolean = $state(false);
  drawingRally: boolean = $state(false);
  kmlOverlay: { type: string; coords: [number, number][]; name: string }[] = $state([]);
  unitSystem: 'metric' | 'imperial' = $state('metric');
}

export const app = new AppState();

export function updateState(s: Partial<DroneState>) {
  if (s.type !== undefined && s.type !== 'state') return;
  // Defense in depth: if WebSerial is the active transport, drone fields are
  // owned by the serial callbacks in ConnectionForm.svelte. A stale WS state
  // arriving (backend slow to release, or a transport-switch race) must not
  // overwrite them. Button-level gate prevents this normally; this catches
  // it if the gate is bypassed.
  if (app.activeTransport === 'serial') return;
  // Nor after a USB drop, while the backend has no vehicle: its zeros would replace the
  // last known position. The backend link keeps its last values through a loss too.
  // A push with a vehicle ends the lost session, whoever connected it.
  if (app.serialLinkLost) {
    if (!s.connected) return;
    app.serialLinkLost = false;
  }
  Object.assign(app.drone, s);
  // FC link gone — release the lock so the user can switch transports.
  if (app.activeTransport === 'ws' && s.connected === false) {
    app.activeTransport = 'none';
  }
}

const PLANE_VTYPE_RAW = new Set([1, 19, 20, 21, 22, 23, 24, 25]);

export function isPlane(): boolean {
  return PLANE_VTYPE_RAW.has(app.drone.vtype_raw);
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
    // Storage is read as a file is: these values reach the map's HTML and the mission upload.
    const s = JSON.parse(localStorage.getItem('argus_settings') || '{}');
    // Not 0, as before. Below 0 is an altitude too: a submarine's.
    const set = (v: unknown) => finiteNumber(v) || null;
    app.defaultAlt = set(s.alt) ?? app.defaultAlt;
    app.defaultSpeed = set(s.speed) ?? app.defaultSpeed;
    app.geoRadius = set(s.radius) ?? app.geoRadius;
    if (typeof s.dark === 'boolean') app.darkTheme = s.dark;
    if (typeof s.muted === 'boolean') app.audioMuted = s.muted;
    if (typeof s.voice === 'boolean') app.voiceEnabled = s.voice;
    if (s.region === 'china' || s.region === 'global') app.mapRegion = s.region;
    if (s.tileSource && typeof s.tileSource === 'string') app.tileSource = s.tileSource;
    if (s.mapMode === '2d' || s.mapMode === '3d') app.mapMode = s.mapMode;
    if (s.unitSystem === 'metric' || s.unitSystem === 'imperial') app.unitSystem = s.unitSystem;
  } catch {}
  // One bad entry discards the list: a route with a point left out is another route. Said out
  // loud, or the route would just be gone at the next start.
  const stored = (key: string, restore: (raw: unknown) => void) => {
    try {
      restore(JSON.parse(localStorage.getItem(key) || '[]'));
    } catch (err) {
      console.warn(`[storage] ${key} not restored:`, err);
      addToast(`${t('toast.loadFail')} (${key})`, 'error', 8000);
    }
  };
  stored('argus_waypoints', (raw) => {
    const wps = cleanWaypoints(raw, app.defaultAlt);
    if (wps.length > 0) app.waypoints = wps;
  });
  stored('argus_fence', (raw) => {
    const fence = cleanPositions(raw);
    if (fence.length > 0) app.fencePolygon = fence;
  });
  stored('argus_rally', (raw) => {
    const rally = cleanRallyPoints(raw, app.defaultAlt);
    if (rally.length > 0) app.rallyPoints = rally;
  });
}

export function saveSettings() {
  try {
    localStorage.setItem(
      'argus_settings',
      JSON.stringify({
        alt: app.defaultAlt,
        speed: app.defaultSpeed,
        radius: app.geoRadius,
        dark: app.darkTheme,
        muted: app.audioMuted,
        voice: app.voiceEnabled,
        region: app.mapRegion,
        tileSource: app.tileSource,
        mapMode: app.mapMode,
        unitSystem: app.unitSystem,
      }),
    );
  } catch {}
}

export function saveWaypoints() {
  try {
    localStorage.setItem('argus_waypoints', JSON.stringify(app.waypoints));
  } catch {}
}

export function saveFence() {
  try {
    localStorage.setItem('argus_fence', JSON.stringify(app.fencePolygon));
  } catch {}
}

export function saveRally() {
  try {
    localStorage.setItem('argus_rally', JSON.stringify(app.rallyPoints));
  } catch {}
}

export function generateCircle(centerLat: number, centerLon: number, radius: number, count: number, alt: number) {
  pushUndo();
  const pts: Waypoint[] = [];
  for (let i = 0; i < count; i++) {
    const angle = (i / count) * 2 * Math.PI;
    const dlat = (radius * Math.cos(angle)) / 111320;
    const dlon = (radius * Math.sin(angle)) / (111320 * Math.cos((centerLat * Math.PI) / 180));
    pts.push({
      lat: centerLat + dlat,
      lon: centerLon + dlon,
      alt,
      drop: false,
      delay: 0,
      speed: 0,
      type: 'wp' as const,
      loiter_param: 0,
    });
  }
  app.waypoints = [...app.waypoints, ...pts];
  saveWaypoints();
}

export function loadDownloadedMission(wps: Waypoint[]) {
  pushUndo();
  app.waypoints = wps.map((w) => ({
    lat: w.lat,
    lon: w.lon,
    alt: w.alt,
    drop: w.drop || false,
    delay: w.delay || 0,
    speed: w.speed || 0,
    type: w.type || 'wp',
    loiter_param: w.loiter_param || 0,
    // What a download preserved of the item, so the next upload sends it back: the camera,
    // servo, ROI and yaw commands, and ArduPilot's radius and yaw params.
    ...(w.p3 !== undefined ? { p3: w.p3 } : {}),
    ...(w.p4 !== undefined ? { p4: w.p4 } : {}),
    ...(w.cmd_servo ? { cmd_servo: w.cmd_servo } : {}),
    ...(w.cmd_roi ? { cmd_roi: w.cmd_roi } : {}),
    ...(w.cmd_cam_trig ? { cmd_cam_trig: w.cmd_cam_trig } : {}),
    ...(w.cmd_yaw ? { cmd_yaw: w.cmd_yaw } : {}),
    ...(w.cmd_vtol ? { cmd_vtol: w.cmd_vtol } : {}),
  }));
  saveWaypoints();
  requestAnimationFrame(() => app.fitRouteFlag++);
}

// Confirm dialog
class ConfirmState {
  visible: boolean = $state(false);
  message: string = $state('');
  danger: boolean = $state(false);
  // Timestamp of the last open — ConfirmDialog ignores confirm inputs for a
  // short arming window so a dialog appearing under an in-flight Enter/click
  // (e.g. a scheduler-due confirm) can't be accepted by accident. On the monotonic
  // clock: a wall clock stepped back would swallow every yes until it caught up.
  shownAt: number = 0;
  _resolve: ((v: boolean) => void) | null = null;
}
export const confirmState = new ConfirmState();

export function showConfirm(message: string, danger = false): Promise<boolean> {
  cancelSlide();
  // A second showConfirm while one is open used to silently overwrite
  // _resolve — the first caller's await hung forever. Resolve it as declined
  // before replacing so no caller ever leaks.
  if (confirmState.visible && confirmState._resolve) {
    confirmState._resolve(false);
  }
  return new Promise((resolve) => {
    confirmState.message = message;
    confirmState.danger = danger;
    confirmState.visible = true;
    confirmState.shownAt = performance.now();
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

/**
 * Slid to the end: what it confirms runs now, and the slide, showing "OK", goes a moment later.
 * It ran 300 ms after the slide before, and the 8 s time-out, or a tap on the backdrop, could
 * fall in between: the slide said OK and nothing was sent.
 */
export function finishSlide(showOkMs = 300) {
  const fn = slideState._onConfirm;
  slideState._onConfirm = null;
  setTimeout(() => {
    // Unless another slide has been asked for meanwhile.
    if (!slideState._onConfirm) slideState.visible = false;
  }, showOkMs);
  fn?.();
}

export function cancelSlide() {
  slideState.visible = false;
  slideState._onConfirm = null;
}

export function resolveConfirm(result: boolean) {
  // Arming window: ignore an affirmative that lands right after the dialog
  // opened — it was almost certainly aimed at something else (typing Enter,
  // a click in flight when a scheduler confirm popped up). Declines pass.
  if (result && performance.now() - confirmState.shownAt < 300) return;
  confirmState.visible = false;
  confirmState._resolve?.(result);
  confirmState._resolve = null;
}

let _toastId = 0;
let _toastTimers = new Map<number, ReturnType<typeof setTimeout>>();
export function addToast(text: string, level: 'info' | 'warn' | 'error' | 'success' = 'info', duration = 4000) {
  const existing = app.toasts.find((t) => t.text === text && t.level === level);
  if (existing) {
    existing.count++;
    const prev = _toastTimers.get(existing.id);
    if (prev) clearTimeout(prev);
    _toastTimers.set(
      existing.id,
      setTimeout(() => {
        const idx = app.toasts.findIndex((t) => t.id === existing.id);
        if (idx >= 0) app.toasts.splice(idx, 1);
        _toastTimers.delete(existing.id);
      }, duration),
    );
    return;
  }
  const id = ++_toastId;
  app.toasts.push({ id, text, level, count: 1 });
  if (app.toasts.length > 5) app.toasts.shift();
  _toastTimers.set(
    id,
    setTimeout(() => {
      const idx = app.toasts.findIndex((t) => t.id === id);
      if (idx >= 0) app.toasts.splice(idx, 1);
      _toastTimers.delete(id);
    }, duration),
  );
}

export function dismissToast(id: number) {
  const idx = app.toasts.findIndex((t) => t.id === id);
  if (idx >= 0) app.toasts.splice(idx, 1);
}
