import type { Map as MapLibreMap } from "maplibre-gl";
import { tickSpecFor } from "./ticks";

type GraticuleFeature = GeoJSON.Feature<GeoJSON.LineString, { axis: "meridian" | "parallel" }>;
export type GraticuleData = GeoJSON.FeatureCollection<
  GeoJSON.LineString,
  GraticuleFeature["properties"]
>;

const MAX_LATITUDE = 85;
const SNAP_MULTIPLE = 8;

export const EMPTY_GRATICULE: GraticuleData = { type: "FeatureCollection", features: [] };

type CacheEntry = { key: string; data: GraticuleData };

const cache = new WeakMap<MapLibreMap, CacheEntry>();

function snapDown(value: number, unit: number): number {
  return Math.floor(value / unit) * unit;
}

function snapUp(value: number, unit: number): number {
  return Math.ceil(value / unit) * unit;
}

function buildLines(
  west: number,
  south: number,
  east: number,
  north: number,
  stepDegrees: number,
): GraticuleData {
  const features: GraticuleFeature[] = [];
  const meridians = Math.round((east - west) / stepDegrees);
  const parallels = Math.round((north - south) / stepDegrees);
  for (let index = 0; index <= meridians; index += 1) {
    const lng = west + index * stepDegrees;
    features.push({
      type: "Feature",
      properties: { axis: "meridian" },
      geometry: {
        type: "LineString",
        coordinates: [
          [lng, south],
          [lng, north],
        ],
      },
    });
  }
  for (let index = 0; index <= parallels; index += 1) {
    const lat = south + index * stepDegrees;
    features.push({
      type: "Feature",
      properties: { axis: "parallel" },
      geometry: {
        type: "LineString",
        coordinates: [
          [west, lat],
          [east, lat],
        ],
      },
    });
  }
  return { type: "FeatureCollection", features };
}

export function graticuleSnapshot(map: MapLibreMap | undefined): GraticuleData {
  if (!map) return EMPTY_GRATICULE;
  const stepDegrees = tickSpecFor(map.getZoom()).majorMinutes / 60;
  const bounds = map.getBounds();
  const spanLng = bounds.getEast() - bounds.getWest();
  const spanLat = bounds.getNorth() - bounds.getSouth();
  const unit = stepDegrees * SNAP_MULTIPLE;
  const west = snapDown(bounds.getWest() - spanLng, unit);
  const east = snapUp(bounds.getEast() + spanLng, unit);
  const south = Math.max(-MAX_LATITUDE, snapDown(bounds.getSouth() - spanLat, unit));
  const north = Math.min(MAX_LATITUDE, snapUp(bounds.getNorth() + spanLat, unit));
  const key = [stepDegrees, west, south, east, north].join("|");
  const cached = cache.get(map);
  if (cached?.key === key) return cached.data;
  const data = buildLines(
    west,
    snapUp(south, stepDegrees),
    east,
    snapDown(north, stepDegrees),
    stepDegrees,
  );
  cache.set(map, { key, data });
  return data;
}
