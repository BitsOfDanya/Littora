"use client";

import { layersForMode, type MapModeId } from "@/config/layers";
import { useMapLayersStore } from "@/state/map-layers-store";
import { useLayerTruth } from "./use-layer-truth";

export function useLayerCounts(mode: MapModeId): { off: number; planned: number } {
  const truthOf = useLayerTruth();
  const visible = useMapLayersStore((state) => state.visible);
  const layers = layersForMode(mode);
  const planned = layers.filter((layer) => truthOf(layer) === "planned").length;
  const off = layers.filter(
    (layer) => layer.legend !== "composite" && truthOf(layer) !== "planned" && !visible[layer.id],
  ).length;
  return { off, planned };
}
