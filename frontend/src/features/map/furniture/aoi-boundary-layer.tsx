"use client";

import { useMemo } from "react";
import { Layer, Source } from "react-map-gl/maplibre";
import { ANCHOR_LABELS_LAYER_ID } from "@/config/basemaps";
import { findAoi } from "@/config/aois";
import type { BBox } from "@/domain/geo";
import { useLayerVisible } from "@/state/map-layers-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { useGroundInk } from "../use-map-palette";

export const AOI_BOUNDARY_LAYER_ID = "aoi-boundary";

const LINE_WIDTH_PX = 1.5;
const DASH_PX: readonly [number, number] = [8, 4];

function boundaryRing([west, south, east, north]: BBox): GeoJSON.Feature<GeoJSON.LineString> {
  return {
    type: "Feature",
    properties: {},
    geometry: {
      type: "LineString",
      coordinates: [
        [west, south],
        [east, south],
        [east, north],
        [west, north],
        [west, south],
      ],
    },
  };
}

export function AoiBoundaryLayer() {
  const aoiId = useWorkspaceStore((state) => state.aoiId);
  const visible = useLayerVisible("aoi-boundary");
  const ink = useGroundInk();
  const bbox = findAoi(aoiId)?.bbox;
  const data = useMemo(() => (bbox ? boundaryRing(bbox) : null), [bbox]);

  if (!data) return null;
  return (
    <Source id="aoi-boundary-ring" type="geojson" data={data}>
      <Layer
        id={AOI_BOUNDARY_LAYER_ID}
        type="line"
        beforeId={ANCHOR_LABELS_LAYER_ID}
        layout={{ visibility: visible ? "visible" : "none", "line-join": "miter" }}
        paint={{
          "line-color": ink.aoi,
          "line-width": LINE_WIDTH_PX,
          "line-dasharray": [DASH_PX[0] / LINE_WIDTH_PX, DASH_PX[1] / LINE_WIDTH_PX],
        }}
      />
    </Source>
  );
}
