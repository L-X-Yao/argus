import { wrapLongitude } from './missionIO';

/** The same bounds both links enforce before a ROI command can enter an ACK wait. */
export function validRoiInput(lat: unknown, lon: unknown, alt: unknown): boolean {
  return (
    typeof lat === 'number' &&
    Number.isFinite(lat) &&
    Math.abs(lat) <= 90 &&
    typeof lon === 'number' &&
    Number.isFinite(lon) &&
    Math.abs(lon) <= 180 &&
    typeof alt === 'number' &&
    Number.isFinite(alt)
  );
}

/** Leaflet and MapLibre can pick on a repeated copy of the world. */
export function normalizePickedPoint(lat: number, lon: number): { lat: number; lon: number } {
  return { lat, lon: wrapLongitude(lon) };
}
