import type { Map as MapLibreMap } from "maplibre-gl";
import type { LngLat } from "@/domain/geo";

const REVEAL_MARGIN_PX = 32;
const REVEAL_DURATION_MS = 400;

export function isInVisibleField(map: MapLibreMap, [lng, lat]: LngLat, margin = 0): boolean {
  const { x, y } = map.project([lng, lat]);
  const { top = 0, right = 0, bottom = 0, left = 0 } = map.getPadding();
  const canvas = map.getCanvas();
  return (
    x >= left + margin &&
    x <= canvas.clientWidth - right - margin &&
    y >= top + margin &&
    y <= canvas.clientHeight - bottom - margin
  );
}

function reducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function revealInVisibleField(map: MapLibreMap, lngLat: LngLat): void {
  if (isInVisibleField(map, lngLat, REVEAL_MARGIN_PX)) return;
  map.easeTo({
    center: [lngLat[0], lngLat[1]],
    duration: reducedMotion() ? 0 : REVEAL_DURATION_MS,
  });
}
