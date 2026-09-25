import type { PickingInfo } from "@deck.gl/core";
import {
  FillStyleExtension,
  type FillStyleExtensionProps,
  PathStyleExtension,
  type PathStyleExtensionProps,
} from "@deck.gl/extensions";
import { GeoJsonLayer, PathLayer, SolidPolygonLayer } from "@deck.gl/layers";
import type { ConfidenceClass } from "@/domain/detection";
import type { LngLat } from "@/domain/geo";
import {
  colorForValue,
  cssColorToRgba,
  hexToRgba,
  isBelowRamp,
  type Rgba,
  type StepRamp,
  withAlpha,
} from "@/features/map/color";
import { type Anchored, UNDER_COASTLINE, UNDER_LABELS } from "@/features/map/deck/anchors";
import type { MapPalette } from "@/features/map/palette";
import {
  CONFIDENCE_INK,
  CONFIDENCE_LINES,
  type ConfidenceLevel,
  type Ground,
  HOTSPOT_ALPHA,
  NO_DATA,
  UNCERTAINTY,
} from "@/features/map/ramps";
import type { HotspotCell } from "./hotspots";

export type CandidateProps = { id: string; confidence: ConfidenceClass; coverage: number };
export type CandidateFeature = GeoJSON.Feature<GeoJSON.Polygon, CandidateProps>;
export type CellDatum = { polygon: readonly LngLat[]; coverage: number; candidateId: string };
export type NoDataDatum = GeoJSON.Feature<GeoJSON.Polygon, { kind: "cloud" | "glint" }>;
export type UncertaintyDatum = GeoJSON.Feature<GeoJSON.Polygon, { uncertainty: number }>;
export type RingDatum = { id: string; path: [number, number][] };

type Hover<T> = (info: PickingInfo<T>) => void;

export type LayerMotion = { fadeMs: number };

const TRANSPARENT: Rgba = [0, 0, 0, 0];
const HIT_COLOR: Rgba = [0, 0, 0, 1];
const HIT_WIDTH_PX = 14;
const CELL_ALPHA = 235;
const HOVER_WIDTH_PX = 2.4;
const SELECTION_WIDTH_PX = 2.6;
const SELECTION_HALO_PX = 6;
const SELECTION_HALO_ALPHA = 0.75;
const FOOTPRINT_WIDTH_PX = 1.3;
const FOOTPRINT_DASH: [number, number] = [1, 2.6];

export const CONFIDENCE_LEVEL: Record<ConfidenceClass, ConfidenceLevel> = {
  likely: "high",
  possible: "medium",
  low: "low",
};

const PATTERNS = {
  nodata: { type: "cross-hatch", angles: [45, 135], strokeWidth: 1, gap: NO_DATA.spacingPx - 1 },
  lowConfidence: { type: "hatch", angle: 45, strokeWidth: 1, gap: 7 },
  uncertaintySparse: {
    type: "hatch",
    angle: 45,
    strokeWidth: UNCERTAINTY.lineWidthPx,
    gap: UNCERTAINTY.spacingPx.sparse - UNCERTAINTY.lineWidthPx,
  },
  uncertaintyDense: {
    type: "hatch",
    angle: 45,
    strokeWidth: UNCERTAINTY.lineWidthPx,
    gap: UNCERTAINTY.spacingPx.dense - UNCERTAINTY.lineWidthPx,
  },
} as const;

function fadeIn(motion: LayerMotion) {
  return {
    duration: motion.fadeMs,
    enter: (value: number[]) => [value[0], value[1], value[2], 0],
  };
}

function patternExtension() {
  return new FillStyleExtension({ pattern: true, proceduralPattern: true });
}

export function noDataLayer(data: readonly NoDataDatum[], ground: Ground, motion: LayerMotion) {
  const ink = NO_DATA.ink[ground];
  const line = withAlpha(hexToRgba(ink.line), NO_DATA.lineAlpha);
  return new GeoJsonLayer<
    NoDataDatum["properties"],
    FillStyleExtensionProps<NoDataDatum> & PathStyleExtensionProps<NoDataDatum> & Anchored
  >({
    id: "monitor:no-data",
    ...UNDER_COASTLINE,
    data: data as NoDataDatum[],
    filled: true,
    stroked: true,
    getFillColor: line,
    fillPatternMapping: PATTERNS,
    fillPatternSizeUnits: "pixels",
    getFillPattern: () => "nodata",
    getFillPatternBackgroundColor: cssColorToRgba(ink.underlay),
    getLineColor: withAlpha(hexToRgba(ink.line), 0.8),
    getLineWidth: NO_DATA.edgeWidthPx,
    lineWidthUnits: "pixels",
    getDashArray: [NO_DATA.edgeDash[0], NO_DATA.edgeDash[1]],
    dashJustified: true,
    extensions: [patternExtension(), new PathStyleExtension({ dash: true })],
    updateTriggers: {
      getFillColor: ground,
      getLineColor: ground,
      getFillPatternBackgroundColor: ground,
    },
    transitions: { getFillColor: fadeIn(motion), getLineColor: fadeIn(motion) },
  });
}

function rampColor(ramp: StepRamp, value: number, alpha: number): Rgba {
  return isBelowRamp(ramp, value) ? TRANSPARENT : hexToRgba(colorForValue(ramp, value), alpha);
}

export function coverageCellsLayer(
  data: readonly CellDatum[],
  ramp: StepRamp,
  motion: LayerMotion,
) {
  return new SolidPolygonLayer<CellDatum, Anchored>({
    id: "monitor:coverage-cells",
    ...UNDER_COASTLINE,
    data: data as CellDatum[],
    getPolygon: (cell) => cell.polygon as [number, number][],
    getFillColor: (cell) => rampColor(ramp, cell.coverage, CELL_ALPHA),
    updateTriggers: { getFillColor: ramp },
    transitions: { getFillColor: fadeIn(motion) },
  });
}

export function hotspotLayer(
  data: readonly HotspotCell[],
  ramp: StepRamp,
  motion: LayerMotion,
  onHover: Hover<HotspotCell>,
  onClick: Hover<HotspotCell>,
) {
  return new SolidPolygonLayer<HotspotCell, Anchored>({
    id: "monitor:hotspots",
    ...UNDER_COASTLINE,
    data: data as HotspotCell[],
    pickable: true,
    getPolygon: (cell) => cell.polygon as [number, number][],
    getFillColor: (cell) => rampColor(ramp, cell.coverage, Math.round(HOTSPOT_ALPHA * 255)),
    updateTriggers: { getFillColor: ramp },
    transitions: { getFillColor: fadeIn(motion) },
    onHover,
    onClick,
  });
}

export function uncertaintyLayer(
  data: readonly UncertaintyDatum[],
  ground: Ground,
  motion: LayerMotion,
) {
  const ink = UNCERTAINTY.ink[ground];
  return new GeoJsonLayer<
    UncertaintyDatum["properties"],
    FillStyleExtensionProps<UncertaintyDatum> & Anchored
  >({
    id: "monitor:uncertainty",
    ...UNDER_COASTLINE,
    data: data as UncertaintyDatum[],
    filled: true,
    stroked: false,
    getFillColor: cssColorToRgba(ink.hatch),
    fillPatternMapping: PATTERNS,
    fillPatternSizeUnits: "pixels",
    getFillPattern: (feature: UncertaintyDatum) =>
      feature.properties.uncertainty > UNCERTAINTY.denseAbove
        ? "uncertaintyDense"
        : "uncertaintySparse",
    extensions: [patternExtension()],
    updateTriggers: { getFillColor: ground },
    transitions: { getFillColor: fadeIn(motion) },
  });
}

function lineStyleOf(feature: { properties: CandidateProps }) {
  return CONFIDENCE_LINES[CONFIDENCE_LEVEL[feature.properties.confidence]];
}

export function candidateOutlineLayer(
  data: readonly CandidateFeature[],
  ground: Ground,
  palette: MapPalette,
  motion: LayerMotion,
  handlers: { onHover: Hover<CandidateFeature>; onClick: Hover<CandidateFeature> },
) {
  const hatch = cssColorToRgba(CONFIDENCE_INK[ground].lowHatch);
  return new GeoJsonLayer<
    CandidateProps,
    FillStyleExtensionProps<CandidateFeature> & PathStyleExtensionProps<CandidateFeature> & Anchored
  >({
    id: "monitor:candidates",
    ...UNDER_COASTLINE,
    data: data as CandidateFeature[],
    pickable: true,
    filled: true,
    stroked: true,
    getFillColor: (feature) => (feature.properties.confidence === "low" ? hatch : TRANSPARENT),
    fillPatternMapping: PATTERNS,
    fillPatternSizeUnits: "pixels",
    getFillPattern: () => "lowConfidence",
    getLineColor: palette.outline,
    getLineWidth: (feature) => lineStyleOf(feature).widthPx,
    lineWidthUnits: "pixels",
    lineJointRounded: true,
    getDashArray: (feature: CandidateFeature) => [...lineStyleOf(feature).dash],
    dashJustified: true,
    extensions: [patternExtension(), new PathStyleExtension({ dash: true })],
    updateTriggers: { getFillColor: ground, getLineColor: palette.outline },
    transitions: { getLineColor: fadeIn(motion) },
    ...handlers,
  });
}

export function candidateHitLayer(
  data: readonly CandidateFeature[],
  handlers: { onHover: Hover<CandidateFeature>; onClick: Hover<CandidateFeature> },
) {
  return new PathLayer<CandidateFeature, Anchored>({
    id: "monitor:candidate-hit",
    ...UNDER_COASTLINE,
    data: data as CandidateFeature[],
    pickable: true,
    getPath: (feature) => feature.geometry.coordinates[0] as [number, number][],
    getColor: HIT_COLOR,
    getWidth: HIT_WIDTH_PX,
    widthUnits: "pixels",
    ...handlers,
  });
}

export function footprintLayer(ring: RingDatum | null, palette: MapPalette) {
  return new PathLayer<RingDatum, PathStyleExtensionProps<RingDatum> & Anchored>({
    id: "monitor:scene-footprint",
    ...UNDER_COASTLINE,
    data: ring ? [ring] : [],
    getPath: (entry) => entry.path,
    getColor: withAlpha(palette.outline, 0.72),
    getWidth: FOOTPRINT_WIDTH_PX,
    widthUnits: "pixels",
    capRounded: true,
    getDashArray: FOOTPRINT_DASH,
    extensions: [new PathStyleExtension({ dash: true })],
    updateTriggers: { getColor: palette.outline },
  });
}

function outlineOnly(id: string, feature: CandidateFeature, color: Rgba, widthPx: number) {
  return new GeoJsonLayer<CandidateProps, Anchored>({
    id,
    ...UNDER_LABELS,
    data: [feature],
    filled: false,
    stroked: true,
    lineWidthUnits: "pixels",
    lineJointRounded: true,
    getLineColor: color,
    getLineWidth: widthPx,
  });
}

export function hoverLayer(feature: CandidateFeature, palette: MapPalette) {
  return outlineOnly("monitor:hover", feature, palette.hover, HOVER_WIDTH_PX);
}

export function selectionLayers(feature: CandidateFeature, palette: MapPalette) {
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
