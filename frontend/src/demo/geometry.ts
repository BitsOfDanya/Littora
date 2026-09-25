import type { LngLat } from "@/domain/geo";
import { type MetricOffset, offsetLngLat, toLocalMeters } from "@/lib/geo/local-metric";

export function curvedCenterline(
  start: LngLat,
  bearingDeg: number,
  lengthM: number,
  bendM: number,
  steps = 14,
): LngLat[] {
  const bearing = (bearingDeg * Math.PI) / 180;
  const along: MetricOffset = [Math.sin(bearing), Math.cos(bearing)];
  const across: MetricOffset = [Math.cos(bearing), -Math.sin(bearing)];
  return Array.from({ length: steps + 1 }, (_, index) => {
    const t = index / steps;
    const distance = t * lengthM;
    const bend = Math.sin(t * Math.PI) * bendM;
    return offsetLngLat(start, [
      along[0] * distance + across[0] * bend,
      along[1] * distance + across[1] * bend,
    ]);
  });
}

export function windrowPolygon(centerline: readonly LngLat[], maxWidthM: number): GeoJSON.Polygon {
  const origin = centerline[0];
  const local = centerline.map((point) => toLocalMeters(origin, point));
  const left: LngLat[] = [];
  const right: LngLat[] = [];
  local.forEach((point, index) => {
    const previous = local[Math.max(index - 1, 0)];
    const next = local[Math.min(index + 1, local.length - 1)];
    const dx = next[0] - previous[0];
    const dy = next[1] - previous[1];
    const length = Math.hypot(dx, dy) || 1;
    const t = index / (local.length - 1);
    const halfWidth = (maxWidthM / 2) * Math.max(Math.sin(t * Math.PI), 0.08);
    const normal: MetricOffset = [-dy / length, dx / length];
    left.push(
      offsetLngLat(origin, [point[0] + normal[0] * halfWidth, point[1] + normal[1] * halfWidth]),
    );
    right.push(
      offsetLngLat(origin, [point[0] - normal[0] * halfWidth, point[1] - normal[1] * halfWidth]),
    );
  });
  const ring = [...left, ...right.reverse()];
  return { type: "Polygon", coordinates: [[...ring, ring[0]].map(([lng, lat]) => [lng, lat])] };
}

export function ellipsePolygon(
  center: LngLat,
  radiusEastM: number,
  radiusNorthM: number,
  rotationDeg: number,
  steps = 48,
): GeoJSON.Polygon {
  const rotation = (rotationDeg * Math.PI) / 180;
  const ring = Array.from({ length: steps }, (_, index) => {
    const angle = (index / steps) * Math.PI * 2;
    const x = Math.cos(angle) * radiusEastM;
    const y = Math.sin(angle) * radiusNorthM;
    return offsetLngLat(center, [
      x * Math.cos(rotation) - y * Math.sin(rotation),
      x * Math.sin(rotation) + y * Math.cos(rotation),
    ]);
  });
  return { type: "Polygon", coordinates: [[...ring, ring[0]].map(([lng, lat]) => [lng, lat])] };
}
