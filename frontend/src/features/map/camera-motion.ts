import type { Map as MapLibreMap } from "maplibre-gl";

const STEP_DURATION_MS = 200;

export function reducedMotion(): boolean {
  return (
    typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

export function motionDuration(durationMs: number): number {
  return reducedMotion() ? 0 : durationMs;
}

export function zoomBy(map: MapLibreMap, delta: 1 | -1): void {
  const options = { duration: motionDuration(STEP_DURATION_MS) };
  if (delta > 0) map.zoomIn(options);
  else map.zoomOut(options);
}

export function resetNorth(map: MapLibreMap): void {
  map.resetNorth({ duration: motionDuration(STEP_DURATION_MS) });
}
