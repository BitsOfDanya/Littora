"use client";

import type { Layer, PickingInfo } from "@deck.gl/core";
import { PathStyleExtension } from "@deck.gl/extensions";
import { GeoJsonLayer, ScatterplotLayer } from "@deck.gl/layers";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useDemoActive } from "@/features/cartouche/use-layer-truth";
import { withAlpha } from "@/features/map/color";
import { type Anchored, UNDER_LABELS } from "@/features/map/deck/anchors";
import { useDeckLayers } from "@/features/map/deck/use-deck-layers";
import { useMapPalette } from "@/features/map/use-map-palette";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { getLabels, type TeamLabel } from "@/lib/api/case";
import { useLayerVisible } from "@/state/map-layers-store";

const DEBRIS_CLASSES = new Set(["likely_debris"]);

function hint(label: TeamLabel): string {
  const { properties } = label;
  if (properties.source === "negatives")
    return `Разметка команды · заведомый фон: ${properties.title} · снимок ${properties.scene_id ?? "—"}`;
  return `Аудит зоны ${properties.zone_id ?? ""}: ${properties.title} · уверенность ${properties.confidence ?? "—"} из 3 · ${properties.date ?? ""}`;
}

export function TeamLabelsLayer() {
  const visible = useLayerVisible("team-labels");
  const demoActive = useDemoActive();
  const palette = useMapPalette();
  const setHint = useStatusHintStore((state) => state.setHint);
  const labels = useQuery({
    queryKey: ["labels"],
    queryFn: ({ signal }) => getLabels(signal),
    staleTime: Infinity,
    enabled: visible,
  });

  const layers = useMemo(() => {
    const list: Layer[] = [];
    const features = labels.data?.features ?? [];
    if (!visible || demoActive || !features.length) return list;
    const onHover = (info: PickingInfo<TeamLabel>) =>
      setHint(info.object ? hint(info.object) : null);
    const polygons = features.filter((feature) => feature.properties.source === "negatives");
    const points = features.filter((feature) => feature.properties.source === "audit");
    list.push(
      new GeoJsonLayer<TeamLabel["properties"], Anchored>({
        id: "team-labels:negatives",
        ...UNDER_LABELS,
        data: { type: "FeatureCollection", features: polygons } as never,
        stroked: true,
        filled: true,
        getFillColor: withAlpha(palette.outline, 0.12),
        getLineColor: palette.outline,
        getLineWidth: 1.2,
        lineWidthUnits: "pixels",
        pickable: true,
        onHover: onHover as never,
        extensions: [new PathStyleExtension({ dash: true })],
        getDashArray: [3, 2],
        dashJustified: true,
      } as never),
      new ScatterplotLayer<TeamLabel, Anchored>({
        id: "team-labels:audit",
        ...UNDER_LABELS,
        data: points,
        getPosition: (feature) => feature.geometry.coordinates as [number, number],
        getRadius: 4,
        radiusUnits: "pixels",
        stroked: true,
        getFillColor: (feature) =>
          DEBRIS_CLASSES.has(feature.properties.class ?? "") ? palette.alarm : palette.outline,
        getLineColor: palette.ground === "dark" ? [0, 0, 0, 200] : [255, 255, 255, 220],
        lineWidthUnits: "pixels",
        getLineWidth: 1,
        pickable: true,
        onHover,
      }),
    );
    return list;
  }, [labels.data, visible, demoActive, palette, setHint]);

  useDeckLayers("team-labels", layers);
  return null;
}
