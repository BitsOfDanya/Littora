"use client";

import { useLayerVisible } from "@/state/map-layers-store";
import { ChartFrame } from "./chart-frame";
import { FrameRule } from "./frame-rule";
import { MapStamp } from "./map-stamp";
import { ScaleBar } from "./scale-bar";
import { SeaLabels } from "./sea-labels";
import { useFurnitureLayout } from "./use-furniture-layout";
import { useMapFurnitureVisible } from "./use-furniture-visible";

export function MapFurniture() {
  const visible = useMapFurnitureVisible();
  const layout = useFurnitureLayout();
  const labelsVisible = useLayerVisible("labels");
  if (!visible) return null;

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      <ChartFrame />
      {labelsVisible ? <SeaLabels interior={layout.labelInterior} /> : null}
      <MapStamp align={layout.phone ? "start" : "center"} style={layout.stamp} />
      <ScaleBar phone={layout.phone} style={layout.scale} />
      {layout.phone ? null : <FrameRule band={layout.frame} />}
    </div>
  );
}

export { useFrameWidth } from "./use-frame-width";
