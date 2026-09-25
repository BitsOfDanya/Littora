import type { LngLat } from "@/domain/geo";

const METERS_PER_DEGREE = 111_320;

export type MetricOffset = readonly [eastM: number, northM: number];

function metersPerDegreeLng(lat: number): number {
  return METERS_PER_DEGREE * Math.cos((lat * Math.PI) / 180);
}

export function offsetLngLat(origin: LngLat, [eastM, northM]: MetricOffset): LngLat {
  return [
    origin[0] + eastM / metersPerDegreeLng(origin[1]),
    origin[1] + northM / METERS_PER_DEGREE,
  ];
}

export function toLocalMeters(origin: LngLat, point: LngLat): MetricOffset {
  return [
    (point[0] - origin[0]) * metersPerDegreeLng(origin[1]),
    (point[1] - origin[1]) * METERS_PER_DEGREE,
  ];
}

export function polygonAreaM2(polygon: GeoJSON.Polygon): number {
  const ring = polygon.coordinates[0] as unknown as LngLat[];
  const origin = ring[0];
  const local = ring.map((point) => toLocalMeters(origin, point));
  let twiceArea = 0;
  for (let index = 0; index < local.length - 1; index += 1) {
    twiceArea += local[index][0] * local[index + 1][1] - local[index + 1][0] * local[index][1];
  }
  return Math.abs(twiceArea) / 2;
}

export function polylineLengthM(points: readonly LngLat[]): number {
  const origin = points[0];
  const local = points.map((point) => toLocalMeters(origin, point));
  return local.slice(1).reduce((total, point, index) => {
    const previous = local[index];
    return total + Math.hypot(point[0] - previous[0], point[1] - previous[1]);
  }, 0);
}

export function centroidOf(points: readonly LngLat[]): LngLat {
  const sum = points.reduce<[number, number]>(
    (acc, [lng, lat]) => [acc[0] + lng, acc[1] + lat],
    [0, 0],
  );
  return [sum[0] / points.length, sum[1] / points.length];
}
