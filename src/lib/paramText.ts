/** Parameter text, as a person's locale and a file write it. */

/** A number as the page's locales write it, or NaN when it is no number.
 *
 * A decimal comma ("1,5" in de, fr, es, pt, ru) is a comma: parseFloat read it as 1, and the
 * wrong value went to the flight controller. Thousands separators are not read — a parameter
 * value has no need of them, and "1,234" means 1234 in one locale and 1.234 in the next.
 */
export function parseParamNumber(text: string): number {
  const t = text.trim();
  if (t === '') return NaN;
  const n = /^[+-]?\d+(?:,\d+)?(?:[eE][+-]?\d+)?$/.test(t) ? Number(t.replace(',', '.')) : Number(t);
  return Number.isFinite(n) ? n : NaN;
}

/** The name and the value of a parameter line, or null when it holds neither.
 *
 * Tab, semicolon and space separate fields, as ArduPilot's and a spreadsheet's files do; a line
 * with none of those splits on commas, as Argus's own CSV export writes it (with dot decimals).
 * "NAME,1,5" stays ambiguous there and reads as 1: the format cannot say which comma is the
 * decimal one, so a comma-decimal file should use tabs, spaces or semicolons.
 */
export function paramLine(line: string): [string, number] | null {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith('#')) return null;
  let fields = trimmed.split(/[\t;]+|\s+/).filter(Boolean);
  if (fields.length < 2) fields = trimmed.split(',').map((f) => f.trim());
  if (fields.length < 2) return null;
  const value = parseParamNumber(fields[1]);
  return Number.isFinite(value) ? [fields[0], value] : null;
}
