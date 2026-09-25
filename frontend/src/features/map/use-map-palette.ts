"use client";

import { useMapLayersStore } from "@/state/map-layers-store";
import { usePreferencesStore } from "@/state/preferences-store";
import { GROUND_INK, type GroundInk, type MapPalette, mapPaletteFor } from "./palette";
import { type Ground, groundOf } from "./ramps";

export function useGround(): Ground {
  const basemapId = useMapLayersStore((state) => state.basemapId);
  const theme = usePreferencesStore((state) => state.theme);
  return groundOf(basemapId, theme);
}

export function useGroundInk(): GroundInk {
  return GROUND_INK[useGround()];
}

export function useMapPalette(): MapPalette {
  return mapPaletteFor(useGround());
}
