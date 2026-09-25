import type { Map as MapLibreMap } from "maplibre-gl";
import type { AreaOfInterest } from "@/domain/aoi";
import type { BBox, LngLat } from "@/domain/geo";
import {
  type Padding,
  standardEasing,
  toPadding,
  useViewportPaddingStore,
} from "./use-viewport-padding";

const TILE_SIZE_PX = 512;
export const AOI_FIT_MS = 600;
export const SELECTION_EASE_MS = 400;
export const DEFAULT_FIT_MAX_ZOOM = 11.5;
export const FIT_MARGIN_PX = 24;

export type CameraTarget = { center: LngLat; zoom: number };

export type FitCandidate = { geometry: GeoJSON.Polygon };

export function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

function mercatorX(lng: number): number {
  return (lng + 180) / 360;
}

function mercatorY(lat: number): number {
  return (180 - (180 / Math.PI) * Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360))) / 360;
}

function latitudeOf(y: number): number {
  return (360 / Math.PI) * Math.atan(Math.exp(((180 - y * 360) * Math.PI) / 180)) - 90;
}

export function targetPadding(map: MapLibreMap): Padding {
  return useViewportPaddingStore.getState().target ?? toPadding(map.getPadding());
}

export function cameraForBounds(
  map: MapLibreMap,
  bbox: BBox,
  padding: Padding,
  maxZoom: number,
): CameraTarget | null {
  const [west, south, east, north] = bbox;
  const container = map.getContainer();
  const availableWidth = container.clientWidth - padding.left - padding.right - 2 * FIT_MARGIN_PX;
  const availableHeight = container.clientHeight - padding.top - padding.bottom - 2 * FIT_MARGIN_PX;
  if (availableWidth <= 0 || availableHeight <= 0) return null;
  const x0 = mercatorX(west);
  const x1 = mercatorX(east);
  const y0 = mercatorY(north);
  const y1 = mercatorY(south);
  const spanX = Math.max(x1 - x0, 1e-9);
  const spanY = Math.max(y1 - y0, 1e-9);
  const zoom = Math.log2(
    Math.min(availableWidth / (spanX * TILE_SIZE_PX), availableHeight / (spanY * TILE_SIZE_PX)),
  );
  const center: LngLat = [(west + east) / 2, latitudeOf((y0 + y1) / 2)];
  return { center, zoom: Math.min(zoom, maxZoom, map.getMaxZoom()) };
}

type FitOptions = { durationMs?: number; maxZoom?: number; padding?: Padding };

export function flyToCamera(
  map: MapLibreMap,
  camera: CameraTarget,
  padding: Padding,
  durationMs: number,
): void {
  map.easeTo({
    center: [camera.center[0], camera.center[1]],
    zoom: camera.zoom,
    padding,
    duration: prefersReducedMotion() ? 0 : durationMs,
    easing: standardEasing,
  });
}

export function fitTo(
  map: MapLibreMap,
  bbox: BBox,
  { durationMs = AOI_FIT_MS, maxZoom = DEFAULT_FIT_MAX_ZOOM, padding }: FitOptions = {},
): void {
  const resolvedPadding = padding ?? targetPadding(map);
  const camera = cameraForBounds(map, bbox, resolvedPadding, maxZoom);
  if (camera) flyToCamera(map, camera, resolvedPadding, durationMs);
}

export function fitAoi(map: MapLibreMap, aoi: AreaOfInterest, durationMs = AOI_FIT_MS): void {
  fitTo(map, aoi.bbox, { durationMs, maxZoom: aoi.zoom + 0.5 });
}

function bboxOfPolygons(polygons: readonly GeoJSON.Polygon[]): BBox {
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  for (const polygon of polygons) {
    for (const [lng, lat] of polygon.coordinates[0] ?? []) {
      west = Math.min(west, lng);
      east = Math.max(east, lng);
      south = Math.min(south, lat);
      north = Math.max(north, lat);
    }
  }
  return [west, south, east, north];
}

export type DefaultFitInput = { aoi: AreaOfInterest; candidates: readonly FitCandidate[] | null };

export function defaultCamera(
  map: MapLibreMap,
  { aoi, candidates }: DefaultFitInput,
  padding: Padding,
): CameraTarget | null {
  if (!candidates || candidates.length === 0)
    return cameraForBounds(map, aoi.bbox, padding, aoi.zoom + 0.5);
  return cameraForBounds(
    map,
    bboxOfPolygons(candidates.map((candidate) => candidate.geometry)),
    padding,
    DEFAULT_FIT_MAX_ZOOM,
  );
}

export function fitDefault(
  map: MapLibreMap,
  input: DefaultFitInput,
  { durationMs = AOI_FIT_MS, padding }: Omit<FitOptions, "maxZoom"> = {},
): void {
  const resolvedPadding = padding ?? targetPadding(map);
  const camera = defaultCamera(map, input, resolvedPadding);
  if (camera) flyToCamera(map, camera, resolvedPadding, durationMs);
}

export function isInVisibleField(
  map: MapLibreMap,
  lngLat: LngLat,
  padding: Padding = targetPadding(map),
): boolean {
  const container = map.getContainer();
  const point = map.project([lngLat[0], lngLat[1]]);
  return (
    point.x >= padding.left &&
    point.x <= container.clientWidth - padding.right &&
    point.y >= padding.top &&
    point.y <= container.clientHeight - padding.bottom
  );
}

export function easeToIfOutside(
  map: MapLibreMap,
  lngLat: LngLat,
  durationMs = SELECTION_EASE_MS,
): void {
  const padding = targetPadding(map);
  if (isInVisibleField(map, lngLat, padding)) return;
  map.easeTo({
    center: [lngLat[0], lngLat[1]],
    padding,
    duration: prefersReducedMotion() ? 0 : durationMs,
    easing: standardEasing,
  });
}

const defaultFitSession = { done: false };

export function isDefaultFitDone(): boolean {
  return defaultFitSession.done;
}

export function fitDefaultOnce(
  map: MapLibreMap,
  input: DefaultFitInput,
  options: Omit<FitOptions, "maxZoom"> = {},
): void {
  if (defaultFitSession.done) return;
  defaultFitSession.done = true;
  fitDefault(map, input, options);
}
