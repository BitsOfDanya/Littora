"use client";

import { usePathname } from "next/navigation";
import { useCallback, useSyncExternalStore } from "react";
import { Layer, Source } from "react-map-gl/maplibre";
import { ANCHOR_LABELS_LAYER_ID } from "@/config/basemaps";
import { findModeByPathname } from "@/config/modes";
import { useLayerVisible } from "@/state/map-layers-store";
import { useMainMap } from "../use-main-map";
import { useGroundInk } from "../use-map-palette";
import { EMPTY_GRATICULE, graticuleSnapshot } from "./graticule-data";

export const GRATICULE_LAYER_ID = "graticule";

function useGraticuleData() {
  const map = useMainMap();
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (!map) return () => undefined;
      map.on("move", onChange);
      return () => map.off("move", onChange);
    },
    [map],
  );
  return useSyncExternalStore(
    subscribe,
    () => graticuleSnapshot(map),
    () => EMPTY_GRATICULE,
  );
}

export function GraticuleLayer() {
  const data = useGraticuleData();
  const inReport = findModeByPathname(usePathname() ?? "")?.id === "models";
  const visible = useLayerVisible("graticule") && !inReport;
  const ink = useGroundInk();

  return (
    <Source id="graticule-lines" type="geojson" data={data}>
      <Layer
        id={GRATICULE_LAYER_ID}
        type="line"
        beforeId={ANCHOR_LABELS_LAYER_ID}
        layout={{ visibility: visible ? "visible" : "none" }}
        paint={{ "line-color": ink.graticule, "line-width": 1 }}
      />
    </Source>
  );
}
