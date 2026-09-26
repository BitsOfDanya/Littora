import type { LngLat } from "@/domain/geo";
import { formatNumber } from "@/lib/format/numbers";

export const EARTH_RADIUS_KM = 6371.0088;

const EARTH_RADIUS_M = EARTH_RADIUS_KM * 1000;
const DEG = Math.PI / 180;
const ARC_STEP_M = 25_000;
const ARC_MAX_STEPS = 128;

export type RulerSegment = {
  from: LngLat;
  to: LngLat;
  meters: number;
  path: LngLat[];
  midpoint: LngLat;
  draft: boolean;
};

function centralAngle([lng1, lat1]: LngLat, [lng2, lat2]: LngLat): number {
  const halfLat = Math.sin(((lat2 - lat1) * DEG) / 2);
  const halfLng = Math.sin(((lng2 - lng1) * DEG) / 2);
  const h = halfLat ** 2 + Math.cos(lat1 * DEG) * Math.cos(lat2 * DEG) * halfLng ** 2;
  return 2 * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function haversineMeters(from: LngLat, to: LngLat): number {
  return centralAngle(from, to) * EARTH_RADIUS_M;
}

export function formatRulerDistance(meters: number): string {
  const rounded = Math.round(meters);
  if (rounded < 1000) return `${formatNumber(rounded)} м`;
  return `${formatNumber(meters / 1000, 2)} км`;
}

function toVector([lng, lat]: LngLat): [number, number, number] {
  const phi = lat * DEG;
  const lambda = lng * DEG;
  return [Math.cos(phi) * Math.cos(lambda), Math.cos(phi) * Math.sin(lambda), Math.sin(phi)];
}

function nearestTurn(lng: number, reference: number): number {
  return lng + 360 * Math.round((reference - lng) / 360);
}

export function interpolateGreatCircle(from: LngLat, to: LngLat, fraction: number): LngLat {
  const angle = centralAngle(from, to);
  if (angle < 1e-12) return from;
  const a = Math.sin((1 - fraction) * angle) / Math.sin(angle);
  const b = Math.sin(fraction * angle) / Math.sin(angle);
  const [x1, y1, z1] = toVector(from);
  const [x2, y2, z2] = toVector(to);
  const x = a * x1 + b * x2;
  const y = a * y1 + b * y2;
  const z = a * z1 + b * z2;
  const lat = Math.atan2(z, Math.hypot(x, y)) / DEG;
  const lng = Math.atan2(y, x) / DEG;
  return [nearestTurn(lng, from[0] + fraction * (to[0] - from[0])), lat];
}

export function greatCirclePath(from: LngLat, to: LngLat): LngLat[] {
  const steps = Math.min(
    ARC_MAX_STEPS,
    Math.max(1, Math.ceil(haversineMeters(from, to) / ARC_STEP_M)),
  );
  if (steps === 1) return [from, to];
  return Array.from({ length: steps + 1 }, (_, index) =>
    index === 0 ? from : index === steps ? to : interpolateGreatCircle(from, to, index / steps),
  );
}

function segment(from: LngLat, to: LngLat, draft: boolean): RulerSegment {
  return {
    from,
    to,
    meters: haversineMeters(from, to),
    path: greatCirclePath(from, to),
    midpoint: interpolateGreatCircle(from, to, 0.5),
    draft,
  };
}

export function rulerSegments(points: readonly LngLat[], cursor: LngLat | null): RulerSegment[] {
  const segments = points.slice(1).map((point, index) => segment(points[index], point, false));
  const last = points.at(-1);
  if (last && cursor) segments.push(segment(last, cursor, true));
  return segments;
}

export function totalMeters(segments: readonly RulerSegment[]): number {
  return segments.reduce((sum, entry) => sum + entry.meters, 0);
}
