import type { Waypoint } from './types';

export interface SurveyMatchResult {
  /** Local Survey index -> downloaded waypoint index. */
  pairs: Map<number, number>;
  owned: Set<number>;
  cost: number;
}

interface FlowEdge {
  to: number;
  rev: number;
  cap: number;
  cost: number;
  local?: number;
  download?: number;
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

function addEdge(graph: FlowEdge[][], from: number, to: number, cost: number, local?: number, download?: number) {
  const forward: FlowEdge = { to, rev: graph[to].length, cap: 1, cost, local, download };
  const backward: FlowEdge = { to: from, rev: graph[from].length, cap: 0, cost: -cost };
  graph[from].push(forward);
  graph[to].push(backward);
}

/** Exact min-cost maximum matching for one candidate-connected component (SPFA augmentation). */
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
  const source = 0;
  const firstDownload = locals.length + 1;
  const sink = firstDownload + downloads.length;
  const graph: FlowEdge[][] = Array.from({ length: sink + 1 }, () => []);
  for (let i = 0; i < locals.length; i++) addEdge(graph, source, i + 1, 0);
  for (let i = 0; i < downloads.length; i++) addEdge(graph, firstDownload + i, sink, 0);
  const downloadNodes = new Map(downloads.map((downloaded, index) => [downloaded, firstDownload + index]));
  for (let i = 0; i < locals.length; i++) {
    const local = locals[i];
    for (const downloaded of downloads) {
      if (sameSurveyMissionPoint(survey[local], wps[downloaded])) {
        addEdge(
          graph,
          i + 1,
          downloadNodes.get(downloaded)!,
          surveyMatchCost(survey[local], wps[downloaded]),
          local,
          downloaded,
        );
      }
    }
  }

  let totalCost = 0;
  for (;;) {
    const dist = Array<number>(graph.length).fill(Infinity);
    const parentNode = Array<number>(graph.length).fill(-1);
    const parentEdge = Array<number>(graph.length).fill(-1);
    const inQueue = Array<boolean>(graph.length).fill(false);
    const queue = [source];
    dist[source] = 0;
    inQueue[source] = true;
    for (let head = 0; head < queue.length; head++) {
      const from = queue[head];
      inQueue[from] = false;
      for (let i = 0; i < graph[from].length; i++) {
        const edge = graph[from][i];
        if (edge.cap <= 0) continue;
        const next = dist[from] + edge.cost;
        if (next + 1e-12 >= dist[edge.to]) continue;
        dist[edge.to] = next;
        parentNode[edge.to] = from;
        parentEdge[edge.to] = i;
        if (!inQueue[edge.to]) {
          inQueue[edge.to] = true;
          queue.push(edge.to);
        }
      }
    }
    if (parentNode[sink] < 0) break;
    totalCost += dist[sink];
    for (let at = sink; at !== source; at = parentNode[at]) {
      const from = parentNode[at];
      const edge = graph[from][parentEdge[at]];
      edge.cap -= 1;
      graph[at][edge.rev].cap += 1;
    }
  }

  for (let node = 1; node < firstDownload; node++) {
    for (const edge of graph[node]) {
      if (edge.local !== undefined && edge.download !== undefined && edge.cap === 0) {
        pairs.set(edge.local, edge.download);
      }
    }
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
