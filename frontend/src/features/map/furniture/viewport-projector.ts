import type { Map as MapLibreMap } from "maplibre-gl";

export type LocalPoint = { x: number; y: number };
export type GeoPoint = { lng: number; lat: number };

export type ViewportProjector = {
  width: number;
  height: number;
  project: (lng: number, lat: number) => LocalPoint;
  unproject: (x: number, y: number) => GeoPoint;
};

export function viewportProjector(map: MapLibreMap, element: HTMLElement): ViewportProjector {
  const container = map.getContainer().getBoundingClientRect();
  const viewport = element.getBoundingClientRect();
  const offsetX = viewport.left - container.left;
  const offsetY = viewport.top - container.top;
  return {
    width: viewport.width,
    height: viewport.height,
    project: (lng, lat) => {
      const point = map.project([lng, lat]);
      return { x: point.x - offsetX, y: point.y - offsetY };
    },
    unproject: (x, y) => {
      const lngLat = map.unproject([x + offsetX, y + offsetY]);
      return { lng: lngLat.lng, lat: lngLat.lat };
    },
  };
}
