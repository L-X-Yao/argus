import type { Waypoint } from './types';

export interface SurveyMatchResult {
  /** Local Survey index -> downloaded waypoint index. */
  pairs: Map<number, number>;
  owned: Set<number>;
  cost: number;
}

function sameSurveyMissionPoint(a: Waypoint, b: Waypoint): boolean {
  if ((a.type || 'wp') !== (b.type || 'wp') || Math.fround(a.alt) !== Math.fround(b.alt)) return false;
  // The wire carries int32 lat/lon (missionUpload.ts:69-70). Allow one step
  // for a link that decodes and re-encodes them (scripts/simulator.py:732-739,
  // :459-460); anything closer than that is the same point on the FC.
  return (
    Math.abs(Math.trunc(a.lat * 1e7) - Math.trunc(b.lat * 1e7)) <= 1 &&
    Math.abs(Math.trunc(a.lon * 1e7) - Math.trunc(b.lon * 1e7)) <= 1
  );
}

function surveyMatchCost(a: Waypoint, b: Waypoint): number {
  return (
    Math.abs((a.speed || 0) - (b.speed || 0)) +
    Math.abs((a.delay || 0) - (b.delay || 0)) +
    (a.drop === b.drop ? 0 : 1) +
    Math.abs((a.loiter_param || 0) - (b.loiter_param || 0))
  );
}

/** Exact min-cost maximum matching for one component, in O(max(locals, downloads)^3). */
function matchComponent(
  locals: number[],
  downloads: number[],
  survey: Waypoint[],
  wps: Waypoint[],
  pairs: Map<number, number>,
): number {
  // Deterministic order for equal-cost assignments.
  locals.sort((a, b) => a - b);
  downloads.sort((a, b) => a - b);
  const size = Math.max(locals.length, downloads.length);
  const allowed = Array.from({ length: locals.length }, () => Array<boolean>(downloads.length).fill(false));
  const costs = Array.from({ length: locals.length }, () => Array<number>(size).fill(0));
  let maxCost = 0;
  for (let i = 0; i < locals.length; i++) {
    for (let j = 0; j < downloads.length; j++) {
      if (!sameSurveyMissionPoint(survey[locals[i]], wps[downloads[j]])) continue;
      allowed[i][j] = true;
      const cost = surveyMatchCost(survey[locals[i]], wps[downloads[j]]);
      costs[i][j] = cost;
      if (cost > maxCost) maxCost = cost;
    }
  }
  // One extra real pair is worth more than every allowed edge's cost combined.
  // Forbidden edges and unmatched local Survey points therefore lose cardinality first.
  const blocked = (maxCost + 1) * (Math.min(locals.length, downloads.length) + 1);
  for (let i = 0; i < locals.length; i++) {
    for (let j = 0; j < size; j++) {
      if (j >= downloads.length || !allowed[i][j]) costs[i][j] = blocked;
    }
  }
  const costAt = (i: number, j: number): number => (i >= locals.length ? 0 : costs[i][j]);

  // Hungarian assignment, 1-indexed. Dummy rows leave downloaded points unmatched
  // for free; dummy columns charge the same cardinality penalty as a forbidden edge.
  const u = new Float64Array(size + 1);
  const v = new Float64Array(size + 1);
  const p = new Int32Array(size + 1);
  const way = new Int32Array(size + 1);
  const minv = new Float64Array(size + 1);
  const used = new Uint8Array(size + 1);
  for (let i = 1; i <= size; i++) {
    p[0] = i;
    let j0 = 0;
    minv.fill(Infinity);
    used.fill(0);
    do {
      used[j0] = 1;
      const i0 = p[j0];
      let delta = Infinity;
      let j1 = 0;
      for (let j = 1; j <= size; j++) {
        if (used[j]) continue;
        const cur = costAt(i0 - 1, j - 1) - u[i0] - v[j];
        if (cur < minv[j]) {
          minv[j] = cur;
          way[j] = j0;
        }
        if (minv[j] < delta) {
          delta = minv[j];
          j1 = j;
        }
      }
      for (let j = 0; j <= size; j++) {
        if (used[j]) {
          u[p[j]] += delta;
          v[j] -= delta;
        } else {
          minv[j] -= delta;
        }
      }
      j0 = j1;
    } while (p[j0] !== 0);
    do {
      const j1 = way[j0];
      p[j0] = p[j1];
      j0 = j1;
    } while (j0 !== 0);
  }

  const assignment = new Int32Array(size + 1);
  for (let j = 1; j <= size; j++) assignment[p[j]] = j;
  let totalCost = 0;
  for (let i = 1; i <= locals.length; i++) {
    const j = assignment[i];
    if (j < 1 || j > downloads.length || !allowed[i - 1][j - 1]) continue;
    pairs.set(locals[i - 1], downloads[j - 1]);
    totalCost += costs[i - 1][j - 1];
  }
  return totalCost;
}

/**
 * Maximum one-to-one ownership matching at minimum total attribute cost. Candidate
 * components are independent, so a 500-point mission decomposes instead of building
 * a 500-by-500 assignment problem unless the candidates really are fully connected.
 */
export function matchSurveyOwnership(survey: Waypoint[], wps: Waypoint[]): SurveyMatchResult {
  const byLocal = survey.map(() => [] as number[]);
  const byDownload = wps.map(() => [] as number[]);
  for (let local = 0; local < survey.length; local++) {
    for (let downloaded = 0; downloaded < wps.length; downloaded++) {
      if (!sameSurveyMissionPoint(survey[local], wps[downloaded])) continue;
      byLocal[local].push(downloaded);
      byDownload[downloaded].push(local);
    }
  }

  const seenLocal = new Set<number>();
  const seenDownload = new Set<number>();
  const pairs = new Map<number, number>();
  let totalCost = 0;
  for (let first = 0; first < survey.length; first++) {
    if (seenLocal.has(first) || byLocal[first].length === 0) continue;
    const locals: number[] = [];
    const downloads: number[] = [];
    const localQueue = [first];
    const downloadQueue: number[] = [];
    seenLocal.add(first);
    while (localQueue.length > 0 || downloadQueue.length > 0) {
      if (localQueue.length > 0) {
        const local = localQueue.pop()!;
        locals.push(local);
        for (const downloaded of byLocal[local]) {
          if (seenDownload.has(downloaded)) continue;
          seenDownload.add(downloaded);
          downloadQueue.push(downloaded);
        }
        continue;
      }
      const downloaded = downloadQueue.pop()!;
      downloads.push(downloaded);
      for (const other of byDownload[downloaded]) {
        if (seenLocal.has(other)) continue;
        seenLocal.add(other);
        localQueue.push(other);
      }
    }
    totalCost += matchComponent(locals, downloads, survey, wps, pairs);
  }
  return { pairs, owned: new Set(pairs.values()), cost: totalCost };
}
