/**
 * The largest of the values, and Infinity when one of them is no number at all.
 *
 * A NaN loses every comparison, so `Math.max(...) > limit` is false for it: the variances
 * of an estimator that has diverged, which the FC sends as NaN, passed every limit.
 */
export function worst(...values: number[]): number {
  return values.every(Number.isFinite) ? Math.max(...values) : Infinity;
}
