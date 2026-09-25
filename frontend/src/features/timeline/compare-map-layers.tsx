"use client";

import type { Layer, PickingInfo } from "@deck.gl/core";
import {
  ClipExtension,
  type ClipExtensionProps,
  PathStyleExtension,
  type PathStyleExtensionProps,
} from "@deck.gl/extensions";
import { TileLayer } from "@deck.gl/geo-layers";
import { BitmapLayer, GeoJsonLayer } from "@deck.gl/layers";
import { useCallback, useEffect, useMemo, useState } from "react";
import { EOX_MAXZOOM, RASTER_TINTS, TILE_URLS } from "@/config/basemaps";
import type { CandidatePass } from "@/data/timeline";
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
import { usePrefersReducedMotion } from "@/features/shell/layout/use-environment";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { useLayerVisible, useMapLayersStore } from "@/state/map-layers-store";
import { usePreferencesStore } from "@/state/preferences-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { type ComparePair, passAt } from "./compare-model";
import { useCompareViewStore } from "./compare-view-store";
import { RasterTintExtension, tintFactors } from "./raster-tint-extension";
import { useCompareData } from "./use-compare";

type SideProps = { candidate: DebrisCandidate; pass: CandidatePass };
type SideFeature = GeoJSON.Feature<GeoJSON.Polygon, SideProps>;
type Bounds = [number, number, number, number];
type SideExtras = PathStyleExtensionProps<SideFeature> & ClipExtensionProps & Anchored;

const OWNER = "timeline:compare";
const MAX_LAT = 85.05;
const MOSAIC_FADE_ZOOM: readonly [number, number] = [6.5, 8.5];
const MOSAIC_MIN_ZOOM = 6;
const FILL_ALPHA = 215;
const A_SIDE_DASH: [number, number] = [5, 3];
const A_SIDE_WIDTH_PX = 1.4;
const A_SIDE_ALPHA = 235;
const HOVER_WIDTH_PX = 2.4;
const SELECTION_WIDTH_PX = 2.6;
const SELECTION_HALO_PX = 6;
const SELECTION_HALO_ALPHA = 0.75;
const TRANSPARENT: Rgba = [0, 0, 0, 0];
const FADE_MS = 150;
const FADE_TRANSITION = { opacity: FADE_MS } as const;

const CONFIDENCE_LEVEL: Record<ConfidenceClass, ConfidenceLevel> = {
  likely: "high",
  possible: "medium",
  low: "low",
};

const clip = new ClipExtension();
const pathStyle = new PathStyleExtension({ dash: true });

function sideBounds(dividerLng: number, side: "a" | "b"): Bounds {
  return side === "a"
    ? [-180, -MAX_LAT, dividerLng, MAX_LAT]
    : [dividerLng, -MAX_LAT, 180, MAX_LAT];
}

function mosaicOpacity(zoom: number): number {
  const [from, to] = MOSAIC_FADE_ZOOM;
  return Math.min(1, Math.max(0, (zoom - from) / (to - from)));
}

function featuresAt(
  candidates: readonly DebrisCandidate[],
  histories: ReturnType<typeof useCompareData>["histories"],
  sceneId: string,
): SideFeature[] {
  return candidates.flatMap((candidate) => {
    const history = histories.find((entry) => entry.candidateId === candidate.id);
    const pass = passAt(history, sceneId);
    if (pass?.state !== "found" || !pass.geometry) return [];
    return [{ type: "Feature", geometry: pass.geometry, properties: { candidate, pass } }];
  });
}

function fillOf(feature: SideFeature, ramp: StepRamp): Rgba {
  const value = feature.properties.pass.coverage?.value ?? 0;
  return isBelowRamp(ramp, value) ? TRANSPARENT : hexToRgba(colorForValue(ramp, value), FILL_ALPHA);
}

function lineOf(feature: SideFeature) {
  return CONFIDENCE_LINES[CONFIDENCE_LEVEL[feature.properties.candidate.confidence.class]];
}

type Interaction = {
  onHover: (info: PickingInfo<SideFeature>) => void;
  onClick: (info: PickingInfo<SideFeature>) => void;
};

type LayerStyle = {
  palette: MapPalette;
  ramp: StepRamp;
  showFill: boolean;
  showOutline: boolean;
  opacity: number;
  transitions: { opacity: number } | undefined;
};

function bSideLayer(
  features: SideFeature[],
  bounds: Bounds | null,
  style: LayerStyle,
  interaction: Interaction,
) {
  return new GeoJsonLayer<SideProps, SideExtras>({
    id: `${OWNER}:b`,
    data: features,
    ...UNDER_COASTLINE,
    pickable: true,
    filled: true,
    stroked: style.showOutline,
    lineWidthUnits: "pixels",
    opacity: style.opacity,
    transitions: style.transitions,
    getFillColor: (feature) =>
      style.showFill ? fillOf(feature as SideFeature, style.ramp) : TRANSPARENT,
    getLineColor: style.palette.outline,
    getLineWidth: (feature) => lineOf(feature as SideFeature).widthPx,
    getDashArray: (feature: SideFeature) => [...lineOf(feature).dash],
    dashJustified: true,
    extensions: bounds ? [pathStyle, clip] : [pathStyle],
    clipBounds: bounds ?? undefined,
    clipByInstance: false,
    updateTriggers: {
      getFillColor: [style.ramp, style.showFill],
      getLineColor: style.palette.outline,
    },
    ...interaction,
  });
}

function aSideLayer(
  features: SideFeature[],
  bounds: Bounds,
  style: LayerStyle,
  interaction: Interaction,
) {
  return new GeoJsonLayer<SideProps, SideExtras>({
    id: `${OWNER}:a`,
    data: features,
    ...UNDER_COASTLINE,
    pickable: true,
    filled: true,
    stroked: true,
    lineWidthUnits: "pixels",
    opacity: style.opacity,
    transitions: style.transitions,
    getFillColor: TRANSPARENT,
    getLineColor: withAlpha(style.palette.outline, A_SIDE_ALPHA / 255),
    getLineWidth: A_SIDE_WIDTH_PX,
    getDashArray: A_SIDE_DASH,
    dashJustified: true,
    extensions: [pathStyle, clip],
    clipBounds: bounds,
    clipByInstance: false,
    updateTriggers: { getLineColor: style.palette.outline },
    ...interaction,
  });
}

function accentLayer(
  id: string,
  features: SideFeature[],
  bounds: Bounds | null,
  color: Rgba,
  widthPx: number,
) {
  return new GeoJsonLayer<SideProps, ClipExtensionProps & Anchored>({
    id,
    data: features,
    ...UNDER_LABELS,
    filled: false,
    stroked: true,
    lineWidthUnits: "pixels",
    lineJointRounded: true,
    getLineColor: color,
    getLineWidth: widthPx,
    extensions: bounds ? [clip] : [],
    clipBounds: bounds ?? undefined,
    clipByInstance: false,
  });
}

type MosaicOptions = {
  bounds: Bounds;
  zoom: number;
  tint: RasterTintExtension;
  nonce: number;
  fade: number;
  transitions: { opacity: number } | undefined;
  onError: () => void;
  onLoad: () => void;
};

function mosaicLayer({
  bounds,
  zoom,
  tint,
  nonce,
  fade,
  transitions,
  onError,
  onLoad,
}: MosaicOptions) {
  return new TileLayer<ImageBitmap, ClipExtensionProps & Anchored>({
    id: `${OWNER}:mosaic-2024:${nonce}`,
    data: TILE_URLS.eox2024,
    ...UNDER_COASTLINE,
    minZoom: MOSAIC_MIN_ZOOM,
    maxZoom: EOX_MAXZOOM,
    tileSize: 256,
    opacity: mosaicOpacity(zoom) * fade,
    visible: zoom >= MOSAIC_FADE_ZOOM[0],
    transitions,
    onTileError: onError,
    onViewportLoad: onLoad,
    extensions: [clip, tint],
    clipBounds: bounds,
    clipByInstance: false,
    renderSubLayers: (props) => {
      const [[west, south], [east, north]] = props.tile.boundingBox;
      return new BitmapLayer<ClipExtensionProps>({
        id: props.id,
        opacity: props.opacity,
        visible: props.visible,
        transitions: props.transitions,
        image: props.data,
        bounds: [west, south, east, north],
        extensions: [clip, tint],
        clipBounds: bounds,
        clipByInstance: false,
      });
    },
  });
}

function useFadeIn(): { fade: number; transitions: { opacity: number } | undefined } {
  const reduced = usePrefersReducedMotion();
  const [fade, setFade] = useState(0);
  const [settled, setSettled] = useState(false);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setFade(1));
    const timer = window.setTimeout(() => setSettled(true), FADE_MS * 2);
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(timer);
    };
  }, []);
  return {
    fade: reduced ? 1 : fade,
    transitions: reduced || settled ? undefined : FADE_TRANSITION,
  };
}

function useSideHover() {
  const map = useMainMap();
  const setHint = useStatusHintStore((state) => state.setHint);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const onHover = useCallback(
    (info: PickingInfo<SideFeature>) => {
      const id = info.object?.properties.candidate.id ?? null;
      setHoveredId((current) => (current === id ? current : id));
      setHint(id ? `${id} — щелчок: динамика пятна между A и B` : null);
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

function useMosaicTint(): RasterTintExtension {
  const theme = usePreferencesStore((state) => state.theme);
  return useMemo(() => new RasterTintExtension(tintFactors(RASTER_TINTS.eox[theme])), [theme]);
}

function useMosaicLayers(enabled: boolean): Layer[] {
  const basemapId = useMapLayersStore((state) => state.basemapId);
  const dividerLng = useCompareViewStore((state) => state.dividerLng);
  const zoom = useCompareViewStore((state) => state.zoom);
  const nonce = useCompareViewStore((state) => state.mosaicNonce);
  const setMosaicLoad = useCompareViewStore((state) => state.setMosaicLoad);
  const tint = useMosaicTint();
  const { fade, transitions } = useFadeIn();
  const onError = useCallback(() => setMosaicLoad("error"), [setMosaicLoad]);
  const onLoad = useCallback(() => setMosaicLoad("ready"), [setMosaicLoad]);
  const show = basemapId === "s2-mosaic" && dividerLng !== null && enabled;

  return useMemo(
    () =>
      show && dividerLng !== null
        ? [
            mosaicLayer({
              bounds: sideBounds(dividerLng, "a"),
              zoom,
              tint,
              nonce,
              fade,
              transitions,
              onError,
              onLoad,
            }),
          ]
        : [],
    [show, dividerLng, zoom, tint, nonce, fade, transitions, onError, onLoad],
  );
}

function useOutlineLayers(pair: ComparePair | null): Layer[] {
  const { candidates, histories } = useCompareData();
  const palette = useMapPalette();
  const showFill = useLayerVisible("coverage");
  const showOutline = useLayerVisible("candidates");
  const dividerLng = useCompareViewStore((state) => state.dividerLng);
  const selectedId = useWorkspaceStore((state) => state.selectedCandidateId);
  const selectCandidate = useWorkspaceStore((state) => state.selectCandidate);
  const { hoveredId, onHover } = useSideHover();
  const { fade, transitions } = useFadeIn();
  const ramp = rampFor("coverage", palette.ground);

  const aFeatures = useMemo(
    () => (pair ? featuresAt(candidates, histories, pair.a.id) : []),
    [candidates, histories, pair],
  );
  const bFeatures = useMemo(
    () => (pair ? featuresAt(candidates, histories, pair.b.id) : []),
    [candidates, histories, pair],
  );

  const onClick = useCallback(
    (info: PickingInfo<SideFeature>) => {
      const candidate = info.object?.properties.candidate;
      if (candidate) selectCandidate(candidate.id);
    },
    [selectCandidate],
  );

  const baseLayers = useMemo(() => {
    const style: LayerStyle = {
      palette,
      ramp,
      showFill,
      showOutline,
      opacity: fade,
      transitions,
    };
    const interaction = { onHover, onClick };
    const layers: Layer[] = [];
    if (bFeatures.length && (showFill || showOutline))
      layers.push(
        bSideLayer(
          bFeatures,
          dividerLng === null ? null : sideBounds(dividerLng, "b"),
          style,
          interaction,
        ),
      );
    if (aFeatures.length && showOutline && dividerLng !== null)
      layers.push(aSideLayer(aFeatures, sideBounds(dividerLng, "a"), style, interaction));
    return layers;
  }, [
    aFeatures,
    bFeatures,
    dividerLng,
    palette,
    ramp,
    showFill,
    showOutline,
    fade,
    transitions,
    onHover,
    onClick,
  ]);

  const accentLayers = useMemo(() => {
    const pick = (features: SideFeature[], id: string | null) =>
      features.filter((feature) => feature.properties.candidate.id === id);
    const aBounds = dividerLng === null ? null : sideBounds(dividerLng, "a");
    const bBounds = dividerLng === null ? null : sideBounds(dividerLng, "b");
    const sides = [
      { key: "a", features: aFeatures, bounds: aBounds },
      { key: "b", features: bFeatures, bounds: bBounds },
    ].filter((side) => side.key === "b" || side.bounds !== null);
    const hovered = hoveredId !== selectedId ? hoveredId : null;
    const layers: Layer[] = [];
    for (const side of sides) {
      const hoverFeatures = pick(side.features, hovered);
      if (hoverFeatures.length)
        layers.push(
          accentLayer(
            `${OWNER}:hover-${side.key}`,
            hoverFeatures,
            side.bounds,
            palette.hover,
            HOVER_WIDTH_PX,
          ),
        );
    }
    for (const side of sides) {
      const selected = pick(side.features, selectedId);
      if (!selected.length) continue;
      layers.push(
        accentLayer(
          `${OWNER}:selection-halo-${side.key}`,
          selected,
          side.bounds,
          withAlpha(palette.halo, SELECTION_HALO_ALPHA),
          SELECTION_HALO_PX,
        ),
        accentLayer(
          `${OWNER}:selection-${side.key}`,
          selected,
          side.bounds,
          palette.selection,
          SELECTION_WIDTH_PX,
        ),
      );
    }
    return layers;
  }, [aFeatures, bFeatures, dividerLng, hoveredId, selectedId, palette]);

  return useMemo(() => [...baseLayers, ...accentLayers], [baseLayers, accentLayers]);
}

export function CompareMapLayers() {
  const { pair, hasCatalog, enoughUsable } = useCompareData();
  const mosaic = useMosaicLayers(!hasCatalog || enoughUsable);
  const outlines = useOutlineLayers(pair);
  const layers = useMemo(() => [...mosaic, ...outlines], [mosaic, outlines]);
  useDeckLayers(OWNER, layers);
  return null;
}
