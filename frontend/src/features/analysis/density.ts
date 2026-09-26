import type { LngLat } from "@/domain/geo";
import type { Rgba } from "@/features/map/color";
import { offsetLngLat, polygonAreaM2, toLocalMeters } from "@/lib/geo/local-metric";
import { type RealZone, zoneAdvice } from "./zones";

export const DENSITY_CELL_M = 1000;

export type DensityClass = { max: number; label: string; color: Rgba };

export const DENSITY_CLASSES: readonly DensityClass[] = [
  { max: 15, label: "низкое", color: [255, 214, 102, 150] },
  { max: 40, label: "умеренное", color: [255, 160, 60, 180] },
  { max: 100, label: "высокое", color: [235, 90, 50, 200] },
  { max: Infinity, label: "очень высокое", color: [200, 30, 60, 220] },
];

export type DensityCell = {
  key: string;
  polygon: LngLat[];
  m2PerKm2: number;
  zones: number;
  densityClass: DensityClass;
};

export function densityClass(value: number): DensityClass {
  return DENSITY_CLASSES.find((entry) => value < entry.max) ?? DENSITY_CLASSES.at(-1)!;
}

function counted(zones: readonly RealZone[]): RealZone[] {
  return zones.filter(
    (zone) =>
      zone.centroid !== null &&
      zone.coverage?.area_m2 !== null &&
      zone.coverage !== null &&
      zoneAdvice(zone).kind !== "not_debris",
  );
}

export function densityCells(zones: readonly RealZone[]): DensityCell[] {
  const used = counted(zones);
  if (!used.length) return [];
  const origin: LngLat = [
    Math.floor(Math.min(...used.map((zone) => zone.centroid![0])) * 10) / 10,
    Math.floor(Math.min(...used.map((zone) => zone.centroid![1])) * 10) / 10,
  ];
  const buckets = new Map<string, { column: number; row: number; sum: number; zones: number }>();
  for (const zone of used) {
    const [x, y] = toLocalMeters(origin, [zone.centroid![0], zone.centroid![1]]);
    const column = Math.floor(x / DENSITY_CELL_M);
    const row = Math.floor(y / DENSITY_CELL_M);
    const key = `${column}:${row}`;
    const bucket = buckets.get(key) ?? { column, row, sum: 0, zones: 0 };
    bucket.sum += zone.coverage?.area_m2 ?? 0;
    bucket.zones += 1;
    buckets.set(key, bucket);
  }
  const cellKm2 = (DENSITY_CELL_M / 1000) ** 2;
  return [...buckets.entries()].map(([key, bucket]) => {
    const x0 = bucket.column * DENSITY_CELL_M;
    const y0 = bucket.row * DENSITY_CELL_M;
    const value = bucket.sum / cellKm2;
    return {
      key,
      polygon: [
        offsetLngLat(origin, [x0, y0]),
        offsetLngLat(origin, [x0 + DENSITY_CELL_M, y0]),
        offsetLngLat(origin, [x0 + DENSITY_CELL_M, y0 + DENSITY_CELL_M]),
        offsetLngLat(origin, [x0, y0 + DENSITY_CELL_M]),
      ],
      m2PerKm2: value,
      zones: bucket.zones,
      densityClass: densityClass(value),
    };
  });
}

export function areaDensity(
  zones: readonly RealZone[],
  area: GeoJSON.Polygon,
  waterShare: number | null,
): { m2: number; waterKm2: number; m2PerKm2: number } | null {
  const used = counted(zones);
  const waterKm2 = (polygonAreaM2(area) / 1e6) * (waterShare ?? 1);
  if (waterKm2 <= 0) return null;
  const m2 = used.reduce((sum, zone) => sum + (zone.coverage?.area_m2 ?? 0), 0);
  return { m2, waterKm2, m2PerKm2: m2 / waterKm2 };
}
