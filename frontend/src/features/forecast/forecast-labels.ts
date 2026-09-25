"use client";

import type { GeoJSONSource, Map as MapLibreMap, SymbolLayerSpecification } from "maplibre-gl";
import { useEffect, useRef } from "react";
import type { BeachingSeverity } from "@/data/forecast";
import type { LngLat } from "@/domain/geo";
import type { GroundInk } from "@/features/map/palette";
import { BEACHING, type Ground } from "@/features/map/ramps";

const SOURCE_ID = "forecast-labels";
const TEXT_LAYER_ID = "forecast-labels";
const BEACH_LAYER_ID = "forecast-beach-labels";
const TEXT_SIZE = 11;
const HALO_PX = 1.4;
const ICON_PX = 13;
const ICON_RATIO = 2;

export type ForecastLabelKind = "horizon" | "horizon-active" | "hindcast" | "beach";

export type ForecastLabel = {
  id: string;
  kind: ForecastLabelKind;
  text: string;
  position: LngLat;
  rank: number;
  severity?: Exclude<BeachingSeverity, "info">;
};

type LabelProps = {
  id: string;
  kind: ForecastLabelKind;
  text: string;
  rank: number;
  icon: string;
  color: string;
};

type LabelState = { labels: readonly ForecastLabel[]; ground: Ground; ink: GroundInk };

function iconName(severity: Exclude<BeachingSeverity, "info">, ground: Ground): string {
  return `forecast-${severity}-${ground}`;
}

function colorOf(label: ForecastLabel, state: LabelState): string {
  if (label.kind === "beach" && label.severity) return BEACHING.ink[state.ground][label.severity];
  if (label.kind === "horizon-active") return state.ink.selection;
  return state.ink.label;
}

function collection(state: LabelState): GeoJSON.FeatureCollection<GeoJSON.Point, LabelProps> {
  return {
    type: "FeatureCollection",
    features: state.labels.map((label) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [label.position[0], label.position[1]] },
      properties: {
        id: label.id,
        kind: label.kind,
        text: label.text,
        rank: label.rank,
        icon: label.severity ? iconName(label.severity, state.ground) : "",
        color: colorOf(label, state),
      },
    })),
  };
}

function drawGlyph(severity: Exclude<BeachingSeverity, "info">, ground: Ground): ImageData | null {
  const size = ICON_PX * ICON_RATIO;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");
  if (!context) return null;
  const ink = BEACHING.ink[ground];
  const center = size / 2;
  const radius = size / 2 - 3;
  context.beginPath();
  if (severity === "alarm") {
    for (let corner = 0; corner < 8; corner += 1) {
      const angle = Math.PI / 8 + (corner * Math.PI) / 4;
      const x = center + radius * Math.cos(angle);
      const y = center + radius * Math.sin(angle);
      if (corner === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    }
  } else {
    context.moveTo(center, center - radius);
    context.lineTo(center + radius, center + radius * 0.8);
    context.lineTo(center - radius, center + radius * 0.8);
  }
  context.closePath();
  context.lineJoin = "round";
  context.lineWidth = 4;
  context.strokeStyle = ink.halo;
  context.stroke();
  context.fillStyle = ink[severity];
  context.fill();
  return context.getImageData(0, 0, size, size);
}

function ensureIcons(map: MapLibreMap) {
  for (const ground of ["dark", "light"] as const) {
    for (const severity of ["alarm", "caution"] as const) {
      const name = iconName(severity, ground);
      if (map.hasImage(name)) continue;
      const image = drawGlyph(severity, ground);
      if (image) map.addImage(name, image, { pixelRatio: ICON_RATIO });
    }
  }
}

function textLayer(ink: GroundInk): SymbolLayerSpecification {
  return {
    id: TEXT_LAYER_ID,
    type: "symbol",
    source: SOURCE_ID,
    filter: ["!=", ["get", "kind"], "beach"],
    layout: {
      "text-field": ["get", "text"],
      "text-font": [
        "case",
        ["==", ["get", "kind"], "horizon-active"],
        ["literal", ["Noto Sans Bold"]],
        ["literal", ["Noto Sans Regular"]],
      ],
      "text-size": TEXT_SIZE,
      "text-letter-spacing": 0.02,
      "text-variable-anchor": ["left", "right", "top", "bottom"],
      "text-radial-offset": 0.75,
      "text-justify": "auto",
      "text-max-width": 18,
      "symbol-sort-key": ["get", "rank"],
      "text-padding": 2,
    },
    paint: {
      "text-color": ["get", "color"],
      "text-halo-color": ink.halo,
      "text-halo-width": HALO_PX,
    },
  };
}

function beachLayer(ink: GroundInk): SymbolLayerSpecification {
  return {
    id: BEACH_LAYER_ID,
    type: "symbol",
    source: SOURCE_ID,
    filter: ["==", ["get", "kind"], "beach"],
    layout: {
      "icon-image": ["get", "icon"],
      "icon-anchor": "center",
      "text-field": ["get", "text"],
      "text-font": ["literal", ["Noto Sans Bold"]],
      "text-size": TEXT_SIZE,
      "text-letter-spacing": 0.02,
      "text-anchor": "left",
      "text-offset": [0.9, 0],
      "text-max-width": 16,
      "symbol-sort-key": ["get", "rank"],
      "text-padding": 2,
    },
    paint: {
      "text-color": ["get", "color"],
      "text-halo-color": ink.halo,
      "text-halo-width": HALO_PX + 0.2,
    },
  };
}

function ensureLayers(map: MapLibreMap, state: LabelState) {
  if (!map.isStyleLoaded()) return;
  ensureIcons(map);
  if (!map.getSource(SOURCE_ID))
    map.addSource(SOURCE_ID, { type: "geojson", data: collection(state) });
  if (!map.getLayer(TEXT_LAYER_ID)) map.addLayer(textLayer(state.ink));
  if (!map.getLayer(BEACH_LAYER_ID)) map.addLayer(beachLayer(state.ink));
}

function removeLayers(map: MapLibreMap) {
  try {
    for (const id of [BEACH_LAYER_ID, TEXT_LAYER_ID]) if (map.getLayer(id)) map.removeLayer(id);
    if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
  } catch {
    return;
  }
}

export function useForecastLabelLayers(map: MapLibreMap | undefined, state: LabelState): void {
  const stateRef = useRef(state);
  const { labels, ground, ink } = state;

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
    if (!map) return;
    const source = map.getSource(SOURCE_ID) as GeoJSONSource | undefined;
    source?.setData(collection({ labels, ground, ink }));
    for (const id of [TEXT_LAYER_ID, BEACH_LAYER_ID]) {
      if (map.getLayer(id)) map.setPaintProperty(id, "text-halo-color", ink.halo);
    }
  }, [map, labels, ground, ink]);
}
