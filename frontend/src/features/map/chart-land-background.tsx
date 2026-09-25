"use client";

import { useEffect } from "react";
import { BACKGROUND_LAYER_ID, findBasemap, OFM_SOURCE_ID } from "@/config/basemaps";
import { useMapLayersStore } from "@/state/map-layers-store";
import { usePreferencesStore } from "@/state/preferences-store";
import { useMainMap } from "./use-main-map";

export function ChartLandBackground() {
  const map = useMainMap();
  const basemapId = useMapLayersStore((state) => state.basemapId);
  const theme = usePreferencesStore((state) => state.theme);
  const land = findBasemap(basemapId).landAfterLoad(theme);

  useEffect(() => {
    if (!map || !land) return;
    let applied = false;
    const applyWhenLoaded = () => {
      if (applied || !map.getLayer(BACKGROUND_LAYER_ID) || !map.getSource(OFM_SOURCE_ID)) return;
      if (!map.isSourceLoaded(OFM_SOURCE_ID)) return;
      map.setPaintProperty(BACKGROUND_LAYER_ID, "background-color", land);
      applied = true;
    };
    const resetOnNewStyle = () => {
      applied = false;
    };
    map.on("sourcedata", applyWhenLoaded);
    map.on("idle", applyWhenLoaded);
    map.on("style.load", resetOnNewStyle);
    applyWhenLoaded();
    return () => {
      map.off("sourcedata", applyWhenLoaded);
      map.off("idle", applyWhenLoaded);
      map.off("style.load", resetOnNewStyle);
    };
  }, [map, land]);

  return null;
}
