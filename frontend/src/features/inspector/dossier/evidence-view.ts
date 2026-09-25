import type { LngLat } from "@/domain/geo";

export const TILE_PX = 256;
const EARTH_CIRCUMFERENCE_M = 40_075_016.686;

export type ChipView = {
  zoom: number;
  tileZoom: number;
  originX: number;
  originY: number;
  width: number;
  height: number;
};

export type ChipTile = { x: number; y: number; z: number; left: number; top: number; size: number };

type ViewOptions = { maxTileZoom: number; minSpanM: number; padding: number };

const DEFAULTS: ViewOptions = { maxTileZoom: 14, minSpanM: 1600, padding: 1.35 };

export function worldX(lng: number, zoom: number): number {
  return ((lng + 180) / 360) * TILE_PX * 2 ** zoom;
}

export function worldY(lat: number, zoom: number): number {
  const radians = (lat * Math.PI) / 180;
  return (
    ((1 - Math.log(Math.tan(radians) + 1 / Math.cos(radians)) / Math.PI) / 2) * TILE_PX * 2 ** zoom
  );
}

export function metersPerPixel(lat: number, zoom: number): number {
  return (EARTH_CIRCUMFERENCE_M * Math.cos((lat * Math.PI) / 180)) / (TILE_PX * 2 ** zoom);
}

export function boundsOf(points: readonly LngLat[]): [LngLat, LngLat] {
  const lngs = points.map((point) => point[0]);
  const lats = points.map((point) => point[1]);
  return [
    [Math.min(...lngs), Math.min(...lats)],
    [Math.max(...lngs), Math.max(...lats)],
  ];
}

export function chipView(
  points: readonly LngLat[],
  width: number,
  height: number,
  options: Partial<ViewOptions> = {},
): ChipView {
  const { maxTileZoom, minSpanM, padding } = { ...DEFAULTS, ...options };
  const [[west, south], [east, north]] = boundsOf(points);
  const centerLng = (west + east) / 2;
  const centerLat = (south + north) / 2;
  const spanX = Math.max(worldX(east, 0) - worldX(west, 0), 1e-9) * padding;
  const spanY = Math.max(worldY(south, 0) - worldY(north, 0), 1e-9) * padding;
  const fitZoom = Math.log2(Math.min(width / spanX, height / spanY));
  const minSpanZoom = Math.log2(
    (EARTH_CIRCUMFERENCE_M * Math.cos((centerLat * Math.PI) / 180)) /
      (TILE_PX * (minSpanM / width)),
  );
  const zoom = Math.min(fitZoom, minSpanZoom, maxTileZoom + 2);
  const tileZoom = Math.min(maxTileZoom, Math.max(0, Math.ceil(zoom)));
  return {
    zoom,
    tileZoom,
    originX: worldX(centerLng, zoom) - width / 2,
    originY: worldY(centerLat, zoom) - height / 2,
    width,
    height,
  };
}

export function projectToChip(view: ChipView, [lng, lat]: LngLat): [number, number] {
  return [worldX(lng, view.zoom) - view.originX, worldY(lat, view.zoom) - view.originY];
}

export function chipTiles(view: ChipView): ChipTile[] {
  const scale = 2 ** (view.zoom - view.tileZoom);
  const size = TILE_PX * scale;
  const count = 2 ** view.tileZoom;
  const firstX = Math.floor(view.originX / size);
  const firstY = Math.floor(view.originY / size);
  const lastX = Math.floor((view.originX + view.width) / size);
  const lastY = Math.floor((view.originY + view.height) / size);
  const tiles: ChipTile[] = [];
  for (let y = Math.max(firstY, 0); y <= Math.min(lastY, count - 1); y += 1)
    for (let x = firstX; x <= lastX; x += 1)
      tiles.push({
        x: ((x % count) + count) % count,
        y,
        z: view.tileZoom,
        left: x * size - view.originX,
        top: y * size - view.originY,
        size,
      });
  return tiles;
}

export function tileUrl(template: string, tile: ChipTile): string {
  return template
    .replace("{z}", String(tile.z))
    .replace("{x}", String(tile.x))
    .replace("{y}", String(tile.y));
}
