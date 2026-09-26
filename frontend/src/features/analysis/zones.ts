import type { Rgba } from "@/features/map/color";
import type { AnalysisLayer, AnalysisListItem, AnalysisZone } from "@/lib/api/analyses";
import { formatNumber } from "@/lib/format/numbers";

export type ZonePoint = readonly [number, number];

export type ZoneFlag = { kind: string; label: string; evidence: readonly string[] };

export type ZoneStability = { agreement: number; views: number };

export type ZoneCoverage = {
  mean: number;
  low: number;
  high: number;
  area_m2: number;
  area_m2_low: number;
  area_m2_high: number;
};

export type RealZone = {
  id: string;
  rank: number;
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon | null;
  centroid: ZonePoint | null;
  pixels: number | null;
  areaM2: number | null;
  probabilityMax: number | null;
  probabilityMean: number | null;
  scl: Readonly<Record<string, number>> | null;
  flags: readonly ZoneFlag[];
  stability: ZoneStability | null;
  coverage: ZoneCoverage | null;
};

const PROBABILITY_RAMP: readonly Rgba[] = [
  [255, 236, 179, 255],
  [255, 214, 102, 255],
  [255, 160, 60, 255],
  [235, 90, 50, 255],
  [200, 30, 60, 255],
];

export const ZONE_RAMP_CSS = `linear-gradient(90deg, ${PROBABILITY_RAMP.slice(1)
  .map(([red, green, blue]) => `rgb(${red},${green},${blue})`)
  .join(", ")})`;

const METERS_PER_DEGREE = 111_320;

export function toRealZones(zones: readonly AnalysisZone[]): RealZone[] {
  return zones.map((zone, index) => {
    const geometry =
      zone.geometry?.type === "Polygon" || zone.geometry?.type === "MultiPolygon"
        ? zone.geometry
        : null;
    return {
      id: zone.id ?? `zone-${index + 1}`,
      rank: index + 1,
      geometry,
      centroid: zone.centroid ? [zone.centroid[0], zone.centroid[1]] : null,
      pixels: zone.pixels ?? null,
      areaM2: zone.area_km2 === undefined ? null : Math.round(zone.area_km2 * 1e6),
      probabilityMax: zone.probability_max ?? null,
      probabilityMean: zone.probability_mean ?? null,
      scl: zone.scl ?? null,
      flags: zone.flags ?? [],
      stability: zone.stability ?? null,
      coverage: zone.coverage ?? null,
    };
  });
}

export function zoneStrength(probability: number | null, threshold: number | null): number {
  if (probability === null) return 0;
  const floor = threshold ?? 0;
  if (floor >= 1) return 1;
  return Math.min(Math.max((probability - floor) / (1 - floor), 0), 1);
}

export function zoneColor(probability: number | null, threshold: number | null): Rgba {
  const scaled = 1 + zoneStrength(probability, threshold) * (PROBABILITY_RAMP.length - 2);
  const lower = Math.floor(scaled);
  const upper = Math.min(lower + 1, PROBABILITY_RAMP.length - 1);
  const fraction = scaled - lower;
  const mix = (index: number) =>
    Math.round(
      PROBABILITY_RAMP[lower][index] * (1 - fraction) + PROBABILITY_RAMP[upper][index] * fraction,
    );
  return [mix(0), mix(1), mix(2), 255];
}

export const FLAG_SHORT: Readonly<Record<string, string>> = {
  vessel: "судно?",
  structure: "сооруж.",
  port: "порт",
  unstable: "неуст.",
};

export function isLikelyNotDebris(zone: RealZone): boolean {
  return zone.flags.some((flag) => flag.kind === "vessel" || flag.kind === "structure");
}

export function formatProbability(value: number | null): string {
  return value === null ? "—" : formatNumber(value, 2);
}

export function zoneLabel(zone: RealZone): string {
  return `${zone.id} · ${formatProbability(zone.probabilityMax)}`;
}

export function ringsOf(geometry: RealZone["geometry"]): ZonePoint[][] {
  if (!geometry) return [];
  const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  return polygons.flatMap((polygon) =>
    polygon.map((ring) => ring.map(([lng, lat]) => [lng, lat] as ZonePoint)),
  );
}

export function zoneBounds(zone: RealZone): [number, number, number, number] | null {
  const points = ringsOf(zone.geometry).flat();
  if (!points.length) return zone.centroid ? [...zone.centroid, ...zone.centroid] : null;
  const lngs = points.map(([lng]) => lng);
  const lats = points.map(([, lat]) => lat);
  return [Math.min(...lngs), Math.min(...lats), Math.max(...lngs), Math.max(...lats)];
}

const LABEL_BOX_PX: readonly [number, number] = [118, 18];
const TILE_PX = 512;

export function declutterLabels(
  zones: readonly RealZone[],
  zoom: number,
  pinnedIds: readonly (string | null)[],
  limit: number,
): RealZone[] {
  const pxPerDegree = (TILE_PX * 2 ** zoom) / 360;
  const project = ([lng, lat]: ZonePoint): ZonePoint => {
    const radians = (lat * Math.PI) / 180;
    return [
      lng * pxPerDegree,
      -Math.log(Math.tan(Math.PI / 4 + radians / 2)) * (180 / Math.PI) * pxPerDegree,
    ];
  };
  const pinned = zones.filter((zone) => pinnedIds.includes(zone.id));
  const ordered = [...pinned, ...zones.filter((zone) => !pinnedIds.includes(zone.id))];
  const kept: { zone: RealZone; at: ZonePoint }[] = [];
  for (const zone of ordered) {
    if (!zone.centroid) continue;
    const isPinned = pinnedIds.includes(zone.id);
    if (!isPinned && kept.length >= limit) break;
    const at = project(zone.centroid);
    const clash = kept.some(
      (entry) =>
        Math.abs(entry.at[0] - at[0]) < LABEL_BOX_PX[0] &&
        Math.abs(entry.at[1] - at[1]) < LABEL_BOX_PX[1],
    );
    if (!clash || isPinned) kept.push({ zone, at });
  }
  return kept.map((entry) => entry.zone);
}

export type ImageFrame = {
  origin: ZonePoint;
  across: ZonePoint;
  down: ZonePoint;
  widthM: number;
  heightM: number;
};

function metersBetween(a: ZonePoint, b: ZonePoint): number {
  const scale = Math.cos((((a[1] + b[1]) / 2) * Math.PI) / 180);
  return Math.hypot((b[0] - a[0]) * scale, b[1] - a[1]) * METERS_PER_DEGREE;
}

export function imageFrame(layer: Pick<AnalysisLayer, "corners">): ImageFrame {
  const [topLeft, topRight, , bottomLeft] = layer.corners.map(
    ([lng, lat]) => [lng, lat] as ZonePoint,
  );
  return {
    origin: topLeft,
    across: [topRight[0] - topLeft[0], topRight[1] - topLeft[1]],
    down: [bottomLeft[0] - topLeft[0], bottomLeft[1] - topLeft[1]],
    widthM: metersBetween(topLeft, topRight),
    heightM: metersBetween(topLeft, bottomLeft),
  };
}

export function toFrameMeters(frame: ImageFrame, [lng, lat]: ZonePoint): ZonePoint {
  const dx = lng - frame.origin[0];
  const dy = lat - frame.origin[1];
  const [ax, ay] = frame.across;
  const [bx, by] = frame.down;
  const determinant = ax * by - ay * bx;
  if (determinant === 0) return [0, 0];
  const u = (dx * by - dy * bx) / determinant;
  const v = (ax * dy - ay * dx) / determinant;
  return [u * frame.widthM, v * frame.heightM];
}

export type CropView = { x: number; y: number; widthM: number; heightM: number; scale: number };

export function cropView(
  frame: ImageFrame,
  points: readonly ZonePoint[],
  width: number,
  height: number,
  minExtentM: number,
): CropView | null {
  if (!points.length || width <= 0 || height <= 0) return null;
  const projected = points.map((point) => toFrameMeters(frame, point));
  const xs = projected.map(([x]) => x);
  const ys = projected.map(([, y]) => y);
  const centerX = (Math.min(...xs) + Math.max(...xs)) / 2;
  const centerY = (Math.min(...ys) + Math.max(...ys)) / 2;
  const spanX = Math.max(Math.max(...xs) - Math.min(...xs), minExtentM) * 1.6;
  const spanY = Math.max(Math.max(...ys) - Math.min(...ys), minExtentM) * 1.6;
  const scale = Math.min(width / spanX, height / spanY);
  const widthM = width / scale;
  const heightM = height / scale;
  return { x: centerX - widthM / 2, y: centerY - heightM / 2, widthM, heightM, scale };
}

export function cropPixel(view: CropView, frame: ImageFrame, point: ZonePoint): ZonePoint {
  const [x, y] = toFrameMeters(frame, point);
  return [(x - view.x) * view.scale, (y - view.y) * view.scale];
}

export function findCurrentMatch<T extends Pick<AnalysisListItem, "stale">>(
  items: readonly T[],
  matches: (item: T) => boolean,
): T | null {
  return items.find((item) => !item.stale && matches(item)) ?? null;
}
