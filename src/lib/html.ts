/**
 * Leaflet writes the string it is given for an icon, a tooltip or a popup with innerHTML.
 * Every value that goes into such a string passes through here first, whatever its type says
 * it is: a mission file, browser storage and the flight controller all supply these values.
 */
const ENTITY: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export function escHtml(value: unknown): string {
  return String(value).replace(/[&<>"']/g, (c) => ENTITY[c]);
}

/**
 * A number for a style or an SVG attribute. Escaping is not enough there: text that stays
 * inside the quotes can still add a declaration of its own, a background to fetch for one.
 */
export function cssNumber(value: unknown): number {
  const n = typeof value === 'number' ? value : Number.NaN;
  return Number.isFinite(n) ? n : 0;
}
