"use client";

import { MapLibreOverlay } from "@deck.gl/maplibre";
import type { Map as MapLibreMap } from "maplibre-gl";
import { useEffect, useMemo, useRef } from "react";
import { useMap } from "react-map-gl/maplibre";
import { flattenDeckLayers, useDeckLayerStore } from "../state/deck-layer-store";

type OverlayEntry = {
  overlay: MapLibreOverlay;
  releaseTimer?: ReturnType<typeof setTimeout>;
};

type OverlayRegistry = WeakMap<MapLibreMap, OverlayEntry>;

const REGISTRY_KEY = Symbol.for("littora.deck-overlays");
const globalScope = globalThis as typeof globalThis & { [REGISTRY_KEY]?: OverlayRegistry };
const overlays: OverlayRegistry = (globalScope[REGISTRY_KEY] ??= new WeakMap());

function acquireOverlay(map: MapLibreMap): MapLibreOverlay {
  const existing = overlays.get(map);
  if (existing) {
    clearTimeout(existing.releaseTimer);
    existing.releaseTimer = undefined;
    return existing.overlay;
  }
  const overlay = new MapLibreOverlay({ interleaved: true, layers: [] });
  map.addControl(overlay);
  overlays.set(map, { overlay });
  return overlay;
}

function releaseOverlay(map: MapLibreMap): void {
  const entry = overlays.get(map);
  if (!entry) return;
  entry.releaseTimer = setTimeout(() => {
    overlays.delete(map);
    if (map.hasControl(entry.overlay)) map.removeControl(entry.overlay);
  }, 0);
}

export function DeckOverlay() {
  const { current: mapRef } = useMap();
  const overlayRef = useRef<MapLibreOverlay | null>(null);
  const groups = useDeckLayerStore((state) => state.groups);
  const order = useDeckLayerStore((state) => state.order);
  const layers = useMemo(() => flattenDeckLayers(groups, order), [groups, order]);
  const layersRef = useRef(layers);

  useEffect(() => {
    const map = mapRef?.getMap();
    if (!map) return;
    const overlay = acquireOverlay(map);
    overlayRef.current = overlay;
    overlay.setProps({ layers: layersRef.current });
    return () => {
      overlayRef.current = null;
      releaseOverlay(map);
    };
  }, [mapRef]);

  useEffect(() => {
    layersRef.current = layers;
    overlayRef.current?.setProps({ layers });
  }, [layers]);

  return null;
}
