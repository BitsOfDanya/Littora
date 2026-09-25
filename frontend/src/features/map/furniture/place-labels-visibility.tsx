"use client";

import { useEffect } from "react";
import { PLACE_LABEL_LAYER_IDS } from "@/config/basemaps";
import { useLayerVisible } from "@/state/map-layers-store";
import { useMainMap } from "../use-main-map";

export function PlaceLabelsVisibility() {
  const map = useMainMap();
  const visible = useLayerVisible("labels");

  useEffect(() => {
    if (!map) return;
    const visibility = visible ? "visible" : "none";
    const apply = () => {
      for (const id of PLACE_LABEL_LAYER_IDS) {
        if (map.getLayer(id) && map.getLayoutProperty(id, "visibility") !== visibility)
          map.setLayoutProperty(id, "visibility", visibility);
      }
    };
    apply();
    map.on("styledata", apply);
    return () => {
      map.off("styledata", apply);
    };
  }, [map, visible]);

  return null;
}
