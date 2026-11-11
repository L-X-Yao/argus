/** Georeferenced images drawn over the 2D map, kept in the browser between visits. */
export interface OrthoOverlay {
  id: number;
  dataUrl: string;
  nwLat: number;
  nwLon: number;
  seLat: number;
  seLon: number;
  opacity: number;
}

const STORAGE_KEY = 'argus_ortho_overlays';

// An entry of another shape is left out. The map layer reads its numbers at every start, and
// so does the panel that could delete it: one such entry would keep the map from drawing.
function load(): OrthoOverlay[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (o) =>
        o &&
        typeof o.id === 'number' &&
        typeof o.dataUrl === 'string' &&
        o.dataUrl.startsWith('data:image/') &&
        typeof o.opacity === 'number' &&
        Number.isFinite(o.opacity) &&
        validOrthoBounds(o),
    );
  } catch {}
  return [];
}

class OrthoState {
  overlays: OrthoOverlay[] = $state(load());
}

export const ortho = new OrthoState();

function persist(): boolean {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(ortho.overlays));
    return true;
  } catch {
    return false;
  }
}

/** False when the browser has no room for it: the overlay then lasts until the page closes. */
export function addOrthoOverlay(overlay: Omit<OrthoOverlay, 'id'>): boolean {
  ortho.overlays.push({ id: Date.now(), ...overlay });
  return persist();
}

export function removeOrthoOverlay(id: number): void {
  const idx = ortho.overlays.findIndex((o) => o.id === id);
  if (idx >= 0) {
    ortho.overlays.splice(idx, 1);
    persist();
  }
}

export function validOrthoBounds(b: { nwLat: number; nwLon: number; seLat: number; seLon: number }): boolean {
  const lat = (v: number) => Number.isFinite(v) && v >= -90 && v <= 90;
  const lon = (v: number) => Number.isFinite(v) && v >= -180 && v <= 180;
  return lat(b.nwLat) && lat(b.seLat) && lon(b.nwLon) && lon(b.seLon) && b.nwLat > b.seLat && b.nwLon < b.seLon;
}
