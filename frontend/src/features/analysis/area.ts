import type { Map as MapLibreMap } from "maplibre-gl";
import type { BBox } from "@/domain/geo";
import { targetPadding } from "@/features/map/camera";

export const MAX_SPAN_DEG = 1;

const round = (value: number) => Math.round(value * 10_000) / 10_000;

export function roundBbox(bbox: BBox): BBox {
  return [round(bbox[0]), round(bbox[1]), round(bbox[2]), round(bbox[3])];
}

export function visibleBounds(map: MapLibreMap): BBox {
  const padding = targetPadding(map);
  const container = map.getContainer();
  const right = container.clientWidth - padding.right;
  const bottom = container.clientHeight - padding.bottom;
  const corners = [
    map.unproject([padding.left, padding.top]),
    map.unproject([right, padding.top]),
    map.unproject([right, bottom]),
    map.unproject([padding.left, bottom]),
  ];
  const lngs = corners.map((corner) => corner.lng);
  const lats = corners.map((corner) => corner.lat);
  return [Math.min(...lngs), Math.min(...lats), Math.max(...lngs), Math.max(...lats)];
}

export function spanTooLarge(bbox: BBox): boolean {
  return bbox[2] - bbox[0] > MAX_SPAN_DEG || bbox[3] - bbox[1] > MAX_SPAN_DEG;
}

export function sameBbox(a: BBox, b: BBox): boolean {
  return a.every((value, index) => Math.abs(value - b[index]) < 1e-6);
}

export function bboxRing(bbox: BBox): [number, number][] {
  const [west, south, east, north] = bbox;
  return [
    [west, south],
    [east, south],
    [east, north],
    [west, north],
    [west, south],
  ];
}
