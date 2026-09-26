import { FORECAST_HORIZONS_H, type ForecastHorizonH } from "@/domain/forecast";
import type { LngLat } from "@/domain/geo";
import { polygonAreaM2, toLocalMeters } from "@/lib/geo/local-metric";

export type Displacement = { distanceM: number; bearingDeg: number };

export function displacementOf(origin: LngLat, target: LngLat): Displacement {
  const [east, north] = toLocalMeters(origin, target);
  const bearing = (Math.atan2(east, north) * 180) / Math.PI;
  return { distanceM: Math.hypot(east, north), bearingDeg: (bearing + 360) % 360 };
}

const COMPASS_8 = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"] as const;

export function compassPoint(bearingDeg: number): (typeof COMPASS_8)[number] {
  const normalized = ((bearingDeg % 360) + 360) % 360;
  return COMPASS_8[Math.round(normalized / 45) % 8];
}

export type EllipseSummary = {
  center: LngLat;
  majorAxisM: number;
  minorAxisM: number;
  areaM2: number;
  orientationDeg: number;
};

export function ellipseOf(polygon: GeoJSON.Polygon): EllipseSummary {
  const ring = polygon.coordinates[0] as unknown as LngLat[];
  const closed =
    ring.length > 1 && ring[0][0] === ring.at(-1)?.[0] && ring[0][1] === ring.at(-1)?.[1];
  const vertices = closed ? ring.slice(0, -1) : ring;
  const origin = vertices[0];
  const local = vertices.map((vertex) => toLocalMeters(origin, vertex));
  let twiceArea = 0;
  let cx = 0;
  let cy = 0;
  let ixx = 0;
  let iyy = 0;
  let ixy = 0;
  local.forEach(([x0, y0], index) => {
    const [x1, y1] = local[(index + 1) % local.length];
    const cross = x0 * y1 - x1 * y0;
    twiceArea += cross;
    cx += (x0 + x1) * cross;
    cy += (y0 + y1) * cross;
    ixx += (y0 * y0 + y0 * y1 + y1 * y1) * cross;
    iyy += (x0 * x0 + x0 * x1 + x1 * x1) * cross;
    ixy += (x0 * y1 + 2 * x0 * y0 + 2 * x1 * y1 + x1 * y0) * cross;
  });
  const area = twiceArea / 2;
  const meanX = cx / (3 * twiceArea);
  const meanY = cy / (3 * twiceArea);
  const varY = ixx / 12 / area - meanY * meanY;
  const varX = iyy / 12 / area - meanX * meanX;
  const covXY = ixy / 24 / area - meanX * meanY;
  const half = (varX + varY) / 2;
  const root = Math.sqrt(((varX - varY) / 2) ** 2 + covXY * covXY);
  const major = half + root;
  const minor = Math.max(half - root, 0);
  const angle = (Math.atan2(major - varX, covXY || 1e-12) * 180) / Math.PI;
  const bearing = (90 - angle + 360) % 180;
  const metersPerDegreeLat = 111_320;
  const metersPerDegreeLng = metersPerDegreeLat * Math.cos((origin[1] * Math.PI) / 180);
  return {
    center: [origin[0] + meanX / metersPerDegreeLng, origin[1] + meanY / metersPerDegreeLat],
    majorAxisM: 4 * Math.sqrt(major),
    minorAxisM: 4 * Math.sqrt(minor),
    areaM2: polygonAreaM2(polygon),
    orientationDeg: bearing,
  };
}

export type Reliability = "high" | "medium" | "low";

export const RELIABILITY_WORD: Record<Reliability, string> = {
  high: "высокая",
  medium: "средняя",
  low: "низкая — ориентир",
};

export const RELIABILITY_LIMIT_H: Record<Exclude<Reliability, "low">, number> = {
  high: 24,
  medium: 48,
};

export function reliabilityOf(horizonH: number): Reliability {
  if (horizonH <= RELIABILITY_LIMIT_H.high) return "high";
  if (horizonH <= RELIABILITY_LIMIT_H.medium) return "medium";
  return "low";
}

export const UNRATED_RELIABILITY = "надёжность сценария не оценена";

export function reliabilityHint(horizonH: number, graded: boolean): string {
  return graded ? `надёжность ${RELIABILITY_WORD[reliabilityOf(horizonH)]}` : UNRATED_RELIABILITY;
}

export const CAUTION_FROM_H = 48;

export function horizonLabel(hours: number): string {
  if (hours === 0) return "T₀";
  return `${hours > 0 ? "+" : "−"}${Math.abs(hours)} ч`;
}

export function shiftIso(iso: string, hours: number): string {
  return new Date(Date.parse(iso) + hours * 3_600_000).toISOString();
}

export function elapsedLabel(fromIso: string, nowMs: number): string {
  const hours = Math.floor((nowMs - Date.parse(fromIso)) / 3_600_000);
  if (hours < 0) return `T₀\u2212${Math.abs(hours)}\u202Fч`;
  if (hours < 48) return `T₀+${hours}\u202Fч`;
  const days = Math.floor(hours / 24);
  const rest = hours % 24;
  return rest ? `T₀+${days}\u202Fсут ${rest}\u202Fч` : `T₀+${days}\u202Fсут`;
}

export function stepHorizon(current: ForecastHorizonH, delta: number): ForecastHorizonH {
  const index = FORECAST_HORIZONS_H.indexOf(current) + delta;
  return FORECAST_HORIZONS_H[Math.min(Math.max(index, 0), FORECAST_HORIZONS_H.length - 1)];
}

export function meanSpeedMs(distanceM: number, hours: number): number {
  return hours > 0 ? distanceM / (hours * 3600) : 0;
}

export function boundsOf(points: readonly LngLat[]): readonly [number, number, number, number] {
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  for (const [lng, lat] of points) {
    west = Math.min(west, lng);
    east = Math.max(east, lng);
    south = Math.min(south, lat);
    north = Math.max(north, lat);
  }
  return [west, south, east, north];
}
