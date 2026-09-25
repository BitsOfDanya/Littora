"use client";

import type {
  ExpressionSpecification,
  GeoJSONSource,
  Map as MapLibreMap,
  SymbolLayerSpecification,
} from "maplibre-gl";
import { useCallback, useEffect, useRef } from "react";
import type { LngLat } from "@/domain/geo";
import { useMapRedraw } from "@/features/map/furniture/use-map-redraw";
import { viewportProjector } from "@/features/map/furniture/viewport-projector";
import type { GroundInk } from "@/features/map/palette";
import { ShellSlot } from "@/features/shell/shell-slots";
import { DemoTag } from "@/ui/demo-mark";

export const LABEL_MIN_ZOOM = 9;

const SOURCE_ID = "monitor-candidate-labels";
const LAYER_ID = "monitor-candidate-labels";
const ACTIVE_LAYER_ID = "monitor-candidate-labels-active";
const TEXT_SIZE = 11;
const TEXT_OFFSET_EM = 0.6;
const HALO_PX = 1.4;
const CHIP_OFFSET = { x: Math.round(TEXT_SIZE * TEXT_OFFSET_EM), y: 9 };
const SOUNDING_SCALE = 0.74;
const TEXT_FIELD: ExpressionSpecification = [
  "format",
  ["get", "main"],
  {},
  ["get", "sub"],
  { "font-scale": SOUNDING_SCALE },
];

export type LabelFeature = GeoJSON.Feature<
  GeoJSON.Point,
  {
    id: string;
    text: string;
    main: string;
    sub: string;
    rank: number;
    active: boolean;
    selected: boolean;
  }
>;

type LabelState = { features: readonly LabelFeature[]; visible: boolean; ink: GroundInk };

function collection(features: readonly LabelFeature[]): GeoJSON.FeatureCollection {
  return { type: "FeatureCollection", features: [...features] };
}

function baseLayer({ visible, ink }: LabelState): SymbolLayerSpecification {
  return {
    id: LAYER_ID,
    type: "symbol",
    source: SOURCE_ID,
    minzoom: LABEL_MIN_ZOOM,
    filter: ["!", ["get", "active"]],
    layout: {
      visibility: visible ? "visible" : "none",
      "text-field": TEXT_FIELD,
      "text-font": ["Noto Sans Regular"],
      "text-size": TEXT_SIZE,
      "text-letter-spacing": 0.02,
      "text-variable-anchor": ["left", "top-left", "bottom-left", "right"],
      "text-radial-offset": TEXT_OFFSET_EM,
      "text-justify": "auto",
      "symbol-sort-key": ["get", "rank"],
      "text-padding": 3,
    },
    paint: {
      "text-color": ink.label,
      "text-halo-color": ink.halo,
      "text-halo-width": HALO_PX,
    },
  };
}

function activeLayer({ visible, ink }: LabelState): SymbolLayerSpecification {
  return {
    id: ACTIVE_LAYER_ID,
    type: "symbol",
    source: SOURCE_ID,
    minzoom: LABEL_MIN_ZOOM,
    filter: ["get", "active"],
    layout: {
      visibility: visible ? "visible" : "none",
      "text-field": TEXT_FIELD,
      "text-font": ["Noto Sans Bold"],
      "text-size": TEXT_SIZE,
      "text-letter-spacing": 0.02,
      "text-anchor": "left",
      "text-offset": [TEXT_OFFSET_EM, 0],
      "text-allow-overlap": true,
    },
    paint: {
      "text-color": ["case", ["get", "selected"], ink.selection, ink.hover],
      "text-halo-color": ink.halo,
      "text-halo-width": HALO_PX + 0.4,
    },
  };
}

function ensureLayers(map: MapLibreMap, state: LabelState) {
  try {
    if (!map.getSource(SOURCE_ID))
      map.addSource(SOURCE_ID, { type: "geojson", data: collection(state.features) });
    if (!map.getLayer(LAYER_ID)) map.addLayer(baseLayer(state));
    if (!map.getLayer(ACTIVE_LAYER_ID)) map.addLayer(activeLayer(state));
  } catch {
    return;
  }
}

function removeLayers(map: MapLibreMap) {
  try {
    if (map.getLayer(ACTIVE_LAYER_ID)) map.removeLayer(ACTIVE_LAYER_ID);
    if (map.getLayer(LAYER_ID)) map.removeLayer(LAYER_ID);
    if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
  } catch {
    return;
  }
}

export function useCandidateLabelLayers(map: MapLibreMap | undefined, state: LabelState) {
  const stateRef = useRef(state);
  const { features, visible, ink } = state;

  useEffect(() => {
    stateRef.current = state;
  });

  useEffect(() => {
    if (!map) return;
    const ensure = () => ensureLayers(map, stateRef.current);
    ensure();
    map.on("styledata", ensure);
    return () => {
      map.off("styledata", ensure);
      removeLayers(map);
    };
  }, [map]);

  useEffect(() => {
    const source = map?.getSource(SOURCE_ID) as GeoJSONSource | undefined;
    source?.setData(collection(features));
  }, [map, features]);

  useEffect(() => {
    if (!map) return;
    const visibility = visible ? "visible" : "none";
    for (const id of [LAYER_ID, ACTIVE_LAYER_ID]) {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visibility);
    }
    if (map.getLayer(LAYER_ID)) {
      map.setPaintProperty(LAYER_ID, "text-color", ink.label);
      map.setPaintProperty(LAYER_ID, "text-halo-color", ink.halo);
    }
    if (map.getLayer(ACTIVE_LAYER_ID)) {
      map.setPaintProperty(ACTIVE_LAYER_ID, "text-color", [
        "case",
        ["get", "selected"],
        ink.selection,
        ink.hover,
      ]);
      map.setPaintProperty(ACTIVE_LAYER_ID, "text-halo-color", ink.halo);
    }
  }, [map, visible, ink]);
}

type ChipTarget = { id: string; point: LngLat };

export function LabelDemoChips({
  map,
  targets,
}: {
  map: MapLibreMap | undefined;
  targets: readonly ChipTarget[];
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const chipRefs = useRef(new Map<string, HTMLSpanElement>());

  const draw = useCallback(() => {
    const root = rootRef.current;
    if (!map || !root) return;
    const projector = viewportProjector(map, root);
    const shown = map.getZoom() >= LABEL_MIN_ZOOM;
    for (const target of targets) {
      const element = chipRefs.current.get(target.id);
      if (!element) continue;
      const { x, y } = projector.project(target.point[0], target.point[1]);
      element.style.transform = `translate(${Math.round(x + CHIP_OFFSET.x)}px, ${Math.round(y + CHIP_OFFSET.y)}px)`;
      element.style.visibility = shown ? "visible" : "hidden";
    }
  }, [map, targets]);

  useMapRedraw(map, rootRef, draw, targets);

  return (
    <ShellSlot region="map-overlay">
      <div
        ref={rootRef}
        aria-hidden
        className="pointer-events-none absolute inset-0 overflow-hidden"
      >
        {targets.map((target) => (
          <span
            key={target.id}
            ref={(element) => {
              if (element) chipRefs.current.set(target.id, element);
              else chipRefs.current.delete(target.id);
            }}
            className="absolute top-0 left-0"
            style={{ visibility: "hidden" }}
          >
            <DemoTag className="bg-surface-panel" />
          </span>
        ))}
      </div>
    </ShellSlot>
  );
}
