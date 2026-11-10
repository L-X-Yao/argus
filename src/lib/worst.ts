/**
 * The largest of the values, and Infinity when one of them is no number at all.
 *
 * A NaN loses every comparison, so `Math.max(...) > limit` is false for it: the variances
 * of an estimator that has diverged, which the FC sends as NaN, passed every limit. And a
 * `-Infinity` is below every limit.
 */
export function worst(...values: number[]): number {
  return values.every(Number.isFinite) ? Math.max(...values) : Infinity;
}

/**
 * An angle in radians brought into -π..π, and NaN when it is no number at all.
 *
 * Without a loop: `while (a > Math.PI) a -= 2 * Math.PI` never ends for an infinite yaw,
 * and the page hung with it.
 */
export function wrapPi(angle: number): number {
  if (!Number.isFinite(angle)) return NaN;
  return angle - 2 * Math.PI * Math.round(angle / (2 * Math.PI));
}
