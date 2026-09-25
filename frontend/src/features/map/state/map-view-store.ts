import { create } from "zustand";
import type { LngLat } from "@/domain/geo";

const EARTH_CIRCUMFERENCE_M = 40_075_016.686;
const TILE_SIZE_PX = 512;
const SCREEN_PIXEL_M = 0.00028;

export function metersPerPixel(latitude: number, zoom: number): number {
  return (
    (EARTH_CIRCUMFERENCE_M * Math.cos((latitude * Math.PI) / 180)) / (TILE_SIZE_PX * 2 ** zoom)
  );
}

type Camera = { center: LngLat; zoom: number; bearing: number };

type MapViewStore = Camera & {
  cursor: LngLat | null;
  isReady: boolean;
  metersPerPixel: number;
  scaleDenominator: number;
  setCursor: (cursor: LngLat | null) => void;
  setCamera: (camera: Camera) => void;
  setReady: (isReady: boolean) => void;
};

export const useMapViewStore = create<MapViewStore>()((set) => ({
  cursor: null,
  center: [0, 0],
  zoom: 0,
  bearing: 0,
  isReady: false,
  metersPerPixel: 0,
  scaleDenominator: 0,
  setCursor: (cursor) => set({ cursor }),
  setCamera: ({ center, zoom, bearing }) => {
    const resolution = metersPerPixel(center[1], zoom);
    set({
      center,
      zoom,
      bearing,
      metersPerPixel: resolution,
      scaleDenominator: resolution / SCREEN_PIXEL_M,
    });
  },
  setReady: (isReady) => set({ isReady }),
}));
