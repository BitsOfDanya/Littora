"use client";

import type { PickingInfo } from "@deck.gl/core";
import { PathStyleExtension, type PathStyleExtensionProps } from "@deck.gl/extensions";
import { GeoJsonLayer } from "@deck.gl/layers";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useCandidates } from "@/data/candidates";
import type { ConfidenceClass, DebrisCandidate } from "@/domain/detection";
import {
  colorForValue,
  hexToRgba,
  isBelowRamp,
  type Rgba,
  type StepRamp,
  withAlpha,
} from "@/features/map/color";
import { type Anchored, UNDER_COASTLINE, UNDER_LABELS } from "@/features/map/deck/anchors";
import { useDeckLayers } from "@/features/map/deck/use-deck-layers";
import type { MapPalette } from "@/features/map/palette";
import { CONFIDENCE_LINES, type ConfidenceLevel, rampFor } from "@/features/map/ramps";
import { useMainMap } from "@/features/map/use-main-map";
import { useMapPalette } from "@/features/map/use-map-palette";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { useLayerVisible } from "@/state/map-layers-store";
import { useWorkspaceStore } from "@/state/workspace-store";

type CandidateProps = { candidate: DebrisCandidate };
type CandidateFeature = GeoJSON.Feature<GeoJSON.Polygon, CandidateProps>;
type CandidateLayerExtras = PathStyleExtensionProps<CandidateFeature> & Anchored;

const CONFIDENCE_LEVEL: Record<ConfidenceClass, ConfidenceLevel> = {
  likely: "high",
  possible: "medium",
  low: "low",
};

const FILL_ALPHA = 215;
const TRANSPARENT: Rgba = [0, 0, 0, 0];
const HOVER_WIDTH_PX = 2.4;
const SELECTION_WIDTH_PX = 2.6;
const SELECTION_HALO_PX = 6;
const SELECTION_HALO_ALPHA = 0.75;

type CandidateStyle = {
  palette: MapPalette;
  ramp: StepRamp;
  showFill: boolean;
  showOutline: boolean;
};

function lineStyleOf(feature: CandidateFeature) {
  return CONFIDENCE_LINES[CONFIDENCE_LEVEL[feature.properties.candidate.confidence.class]];
}

function fillColorOf(feature: CandidateFeature, ramp: StepRamp): Rgba {
  const coverage = feature.properties.candidate.coverage.value;
  return isBelowRamp(ramp, coverage)
    ? TRANSPARENT
    : hexToRgba(colorForValue(ramp, coverage), FILL_ALPHA);
}

function toFeatures(candidates: readonly DebrisCandidate[]): CandidateFeature[] {
  return candidates.map((candidate) => ({
    type: "Feature",
    geometry: candidate.geometry,
    properties: { candidate },
  }));
}

function candidatesLayer(
  features: CandidateFeature[],
  { palette, ramp, showFill, showOutline }: CandidateStyle,
  onHover: (info: PickingInfo<CandidateFeature>) => void,
  onClick: (info: PickingInfo<CandidateFeature>) => void,
) {
  return new GeoJsonLayer<CandidateProps, CandidateLayerExtras>({
    id: "monitor:candidates",
    data: features,
    ...UNDER_COASTLINE,
    pickable: true,
    filled: true,
    stroked: showOutline,
    lineWidthUnits: "pixels",
    getFillColor: (feature) =>
      showFill ? fillColorOf(feature as CandidateFeature, ramp) : TRANSPARENT,
    getLineColor: palette.outline,
    getLineWidth: (feature) => lineStyleOf(feature as CandidateFeature).widthPx,
    getDashArray: (feature: CandidateFeature) => [...lineStyleOf(feature).dash],
    dashJustified: true,
    extensions: [new PathStyleExtension({ dash: true })],
    updateTriggers: { getFillColor: [ramp, showFill], getLineColor: palette.outline },
    onHover,
    onClick,
  });
}

function outlineOnly(id: string, feature: CandidateFeature, color: Rgba, widthPx: number) {
  return new GeoJsonLayer<CandidateProps, Anchored>({
    id,
    data: [feature],
    ...UNDER_LABELS,
    filled: false,
    stroked: true,
    lineWidthUnits: "pixels",
    lineJointRounded: true,
    getLineColor: color,
    getLineWidth: widthPx,
  });
}

function selectionLayers(feature: CandidateFeature, palette: MapPalette) {
  return [
    outlineOnly(
      "monitor:selection-halo",
      feature,
      withAlpha(palette.halo, SELECTION_HALO_ALPHA),
      SELECTION_HALO_PX,
    ),
    outlineOnly("monitor:selection", feature, palette.selection, SELECTION_WIDTH_PX),
  ];
}

function useCandidateHover() {
  const map = useMainMap();
  const setHint = useStatusHintStore((state) => state.setHint);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const onHover = useCallback(
    (info: PickingInfo<CandidateFeature>) => {
      const id = info.object?.properties.candidate.id ?? null;
      setHoveredId((current) => (current === id ? current : id));
      setHint(id ? `${id} — щелчок: открыть досье` : null);
      if (map) map.getCanvas().style.cursor = id ? "pointer" : "";
    },
    [map, setHint],
  );

  useEffect(
    () => () => {
      setHint(null);
      if (map) map.getCanvas().style.cursor = "";
    },
    [map, setHint],
  );

  return { hoveredId, onHover };
}

export function CandidateLayers() {
  const sourced = useCandidates();
  const palette = useMapPalette();
  const showFill = useLayerVisible("coverage");
  const showOutline = useLayerVisible("candidates");
  const selectedId = useWorkspaceStore((state) => state.selectedCandidateId);
  const selectCandidate = useWorkspaceStore((state) => state.selectCandidate);
  const { hoveredId, onHover } = useCandidateHover();
  const ramp = rampFor("coverage", palette.ground);

  const features = useMemo(
    () => (sourced.origin === "none" ? [] : toFeatures(sourced.data)),
    [sourced],
  );

  const onClick = useCallback(
    (info: PickingInfo<CandidateFeature>) => {
      const candidate = info.object?.properties.candidate;
      if (candidate) selectCandidate(candidate.id);
    },
    [selectCandidate],
  );

  const baseLayers = useMemo(
    () =>
      features.length && (showFill || showOutline)
        ? [candidatesLayer(features, { palette, ramp, showFill, showOutline }, onHover, onClick)]
        : [],
    [features, palette, ramp, showFill, showOutline, onHover, onClick],
  );

  const accentLayers = useMemo(() => {
    const byId = (id: string | null) =>
      features.find((feature) => feature.properties.candidate.id === id);
    const hovered = hoveredId !== selectedId ? byId(hoveredId) : undefined;
    const selected = byId(selectedId);
    return [
      ...(hovered ? [outlineOnly("monitor:hover", hovered, palette.hover, HOVER_WIDTH_PX)] : []),
      ...(selected ? selectionLayers(selected, palette) : []),
    ];
  }, [features, hoveredId, selectedId, palette]);

  const layers = useMemo(() => [...baseLayers, ...accentLayers], [baseLayers, accentLayers]);
  useDeckLayers("monitor:candidates", layers);
  return null;
}
