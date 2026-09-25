"use client";

import type { PickingInfo } from "@deck.gl/core";
import { PathStyleExtension, type PathStyleExtensionProps } from "@deck.gl/extensions";
import { GeoJsonLayer } from "@deck.gl/layers";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useCandidates } from "@/data/candidates";
import type { ConfidenceClass, DebrisCandidate } from "@/domain/detection";
import { withAlpha } from "@/features/map/color";
import { type Anchored, UNDER_COASTLINE, UNDER_LABELS } from "@/features/map/deck/anchors";
import { useDeckLayers } from "@/features/map/deck/use-deck-layers";
import type { MapPalette } from "@/features/map/palette";
import { CONFIDENCE_LINES, type ConfidenceLevel } from "@/features/map/ramps";
import { useMainMap } from "@/features/map/use-main-map";
import { useMapPalette } from "@/features/map/use-map-palette";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { useLayerVisible } from "@/state/map-layers-store";
import { useWorkspaceStore } from "@/state/workspace-store";

type CandidateProps = { candidate: DebrisCandidate };
type CandidateFeature = GeoJSON.Feature<GeoJSON.Polygon, CandidateProps>;

const LEVEL: Record<ConfidenceClass, ConfidenceLevel> = {
  likely: "high",
  possible: "medium",
  low: "low",
};

const HOVER_WIDTH_PX = 2.4;
const SELECTION_WIDTH_PX = 2.6;
const SELECTION_HALO_PX = 6;

function lineStyle(feature: CandidateFeature) {
  return CONFIDENCE_LINES[LEVEL[feature.properties.candidate.confidence.class]];
}

function outlinesLayer(
  features: CandidateFeature[],
  palette: MapPalette,
  onHover: (info: PickingInfo<CandidateFeature>) => void,
  onClick: (info: PickingInfo<CandidateFeature>) => void,
) {
  return new GeoJsonLayer<CandidateProps, PathStyleExtensionProps<CandidateFeature> & Anchored>({
    id: "forecast:candidates",
    ...UNDER_COASTLINE,
    data: features,
    pickable: true,
    filled: true,
    stroked: true,
    getFillColor: [0, 0, 0, 0],
    getLineColor: palette.outline,
    getLineWidth: (feature) => lineStyle(feature as CandidateFeature).widthPx,
    lineWidthUnits: "pixels",
    getDashArray: (feature: CandidateFeature) => [...lineStyle(feature).dash],
    dashJustified: true,
    extensions: [new PathStyleExtension({ dash: true })],
    updateTriggers: { getLineColor: palette.outline },
    onHover,
    onClick,
  });
}

function outline(
  id: string,
  feature: CandidateFeature,
  color: MapPalette["selection"],
  width: number,
) {
  return new GeoJsonLayer<CandidateProps, Anchored>({
    id,
    ...UNDER_LABELS,
    data: [feature],
    filled: false,
    stroked: true,
    lineWidthUnits: "pixels",
    lineJointRounded: true,
    getLineColor: color,
    getLineWidth: width,
  });
}

export function ForecastCandidates() {
  const map = useMainMap();
  const sourced = useCandidates();
  const palette = useMapPalette();
  const visible = useLayerVisible("candidates");
  const selectedId = useWorkspaceStore((state) => state.selectedCandidateId);
  const selectCandidate = useWorkspaceStore((state) => state.selectCandidate);
  const setHint = useStatusHintStore((state) => state.setHint);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const features = useMemo<CandidateFeature[]>(
    () =>
      sourced.origin === "none"
        ? []
        : sourced.data.map((candidate) => ({
            type: "Feature",
            geometry: candidate.geometry,
            properties: { candidate },
          })),
    [sourced],
  );

  const onHover = useCallback(
    (info: PickingInfo<CandidateFeature>) => {
      const id = info.object?.properties.candidate.id ?? null;
      setHoveredId((current) => (current === id ? current : id));
      setHint(
        id
          ? id === useWorkspaceStore.getState().selectedCandidateId
            ? `${id} — прогноз построен`
            : `${id} — щелчок: построить прогноз`
          : null,
      );
      if (map) map.getCanvas().style.cursor = id ? "pointer" : "";
    },
    [map, setHint],
  );

  const onClick = useCallback(
    (info: PickingInfo<CandidateFeature>) => {
      const candidate = info.object?.properties.candidate;
      if (candidate) selectCandidate(candidate.id);
    },
    [selectCandidate],
  );

  useEffect(
    () => () => {
      if (map) map.getCanvas().style.cursor = "";
    },
    [map],
  );

  const layers = useMemo(() => {
    if (!features.length) return [];
    const byId = (id: string | null) =>
      features.find((feature) => feature.properties.candidate.id === id);
    const hovered = hoveredId !== selectedId ? byId(hoveredId) : undefined;
    const selected = byId(selectedId);
    return [
      ...(visible ? [outlinesLayer(features, palette, onHover, onClick)] : []),
      ...(hovered && visible
        ? [outline("forecast:candidate-hover", hovered, palette.hover, HOVER_WIDTH_PX)]
        : []),
      ...(selected
        ? [
            outline(
              "forecast:selection-halo",
              selected,
              withAlpha(palette.halo, 0.75),
              SELECTION_HALO_PX,
            ),
            outline("forecast:selection", selected, palette.selection, SELECTION_WIDTH_PX),
          ]
        : []),
    ];
  }, [features, visible, palette, hoveredId, selectedId, onHover, onClick]);

  useDeckLayers("forecast:candidates", layers);
  return null;
}
