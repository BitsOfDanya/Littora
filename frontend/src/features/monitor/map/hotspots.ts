import type { LngLat } from "@/domain/geo";
import { offsetLngLat, toLocalMeters } from "@/lib/geo/local-metric";

export const HOTSPOT_CELL_M = 1000;
const HOTSPOT_ORIGIN: LngLat = [-180, 0];

export type HotspotSource = { candidateId: string; center: LngLat; coverage: number };

export type HotspotCell = {
  key: string;
  polygon: LngLat[];
  coverage: number;
  cellCount: number;
  candidateIds: string[];
};

function gridOrigin(sources: readonly HotspotSource[]): LngLat {
  if (!sources.length) return HOTSPOT_ORIGIN;
  const west = Math.min(...sources.map((source) => source.center[0]));
  const south = Math.min(...sources.map((source) => source.center[1]));
  return [Math.floor(west * 10) / 10, Math.floor(south * 10) / 10];
}

export function aggregateHotspots(sources: readonly HotspotSource[]): HotspotCell[] {
  const origin = gridOrigin(sources);
  const buckets = new Map<
    string,
    { column: number; row: number; sum: number; count: number; weights: Map<string, number> }
  >();
  for (const source of sources) {
    const [x, y] = toLocalMeters(origin, source.center);
    const column = Math.floor(x / HOTSPOT_CELL_M);
    const row = Math.floor(y / HOTSPOT_CELL_M);
    const key = `${column}:${row}`;
    const bucket = buckets.get(key) ?? { column, row, sum: 0, count: 0, weights: new Map() };
    bucket.sum += source.coverage;
    bucket.count += 1;
    bucket.weights.set(
      source.candidateId,
      (bucket.weights.get(source.candidateId) ?? 0) + source.coverage,
    );
    buckets.set(key, bucket);
  }
  return [...buckets.entries()].map(([key, bucket]) => {
    const x0 = bucket.column * HOTSPOT_CELL_M;
    const y0 = bucket.row * HOTSPOT_CELL_M;
    const x1 = x0 + HOTSPOT_CELL_M;
    const y1 = y0 + HOTSPOT_CELL_M;
    return {
      key,
      polygon: [
        offsetLngLat(origin, [x0, y0]),
        offsetLngLat(origin, [x1, y0]),
        offsetLngLat(origin, [x1, y1]),
        offsetLngLat(origin, [x0, y1]),
      ],
      coverage: bucket.sum / bucket.count,
      cellCount: bucket.count,
      candidateIds: [...bucket.weights.entries()]
        .sort((a, b) => b[1] - a[1])
        .map(([candidateId]) => candidateId),
    };
  });
}
