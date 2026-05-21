const SETTINGS_KEY = 'pllink_v3_settings';
const WP_KEY = 'pllink_v3_waypoints';

export interface SettingsData {
  alt: number;
  speed: number;
  radius: number;
  dark: boolean;
  muted: boolean;
  voice: boolean;
  region: string;
  units: string;
}

export function loadSettingsData(): Partial<SettingsData> {
  try {
    return JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}');
  } catch { return {}; }
}

export function saveSettingsData(data: SettingsData) {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(data));
  } catch {}
}

export function loadWaypointsData(): any[] {
  try {
    const wps = JSON.parse(localStorage.getItem(WP_KEY) || '[]');
    return Array.isArray(wps) ? wps : [];
  } catch { return []; }
}

export function saveWaypointsData(wps: any[]) {
  try {
    localStorage.setItem(WP_KEY, JSON.stringify(wps));
  } catch {}
}
