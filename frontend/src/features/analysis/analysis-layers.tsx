"use client";

import type { Layer, PickingInfo } from "@deck.gl/core";
import { PathStyleExtension, type PathStyleExtensionProps } from "@deck.gl/extensions";
import { BitmapLayer, GeoJsonLayer, PathLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { useCallback, useEffect, useMemo } from "react";
import type { SceneSummary } from "@/domain/scene";
import { useDemoActive } from "@/features/cartouche/use-layer-truth";
import { type Rgba, withAlpha } from "@/features/map/color";
import { type Anchored, UNDER_COASTLINE, UNDER_LABELS } from "@/features/map/deck/anchors";
import { useDeckLayers } from "@/features/map/deck/use-deck-layers";
import type { MapPalette } from "@/features/map/palette";
import { useMainMap } from "@/features/map/use-main-map";
import { useMapPalette } from "@/features/map/use-map-palette";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { useSelectedScene } from "@/features/time-rail/use-selected-scene";
import { type Analysis, analysisFileUrl, type ResultStatus } from "@/lib/api/analyses";
import { useAnalysisStore } from "@/state/analysis-store";
import { useLayerOpacity, useLayerVisible, useMapLayersStore } from "@/state/map-layers-store";
import { CONCENTRATION_UNIT, profileLabel } from "./analysis-copy";
import { formatConcentration, formatDay } from "./format";
import { useCurrentAnalysis } from "./use-analysis";
import { type TimedObservation, useObservationsView } from "./use-observations-view";

type Ring = { id: string; path: [number, number][] };
type Segment = { id: string; path: [number, number][]; faded: boolean };

const AREA_DASH: [number, number] = [5, 3];
const FOOTPRINT_DASH: [number, number] = [1, 2.6];
const LABEL_FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
const LABEL_CHARACTERS = "0123456789,.";
const HALO_PX = 2;
const SELECTION_RING_PX = 5;

function markerRadius(value: number | null): number {
  return 4 + 2.2 * Math.log10(1 + Math.max(value ?? 0, 0));
}

function labelText(value: number | null): string {
  if (value === null) return "";
  return value >= 10 ? String(Math.round(value)) : value.toFixed(1).replace(".", ",");
}

function statusColor(status: ResultStatus, palette: MapPalette): Rgba {
  if (status === "detected") return palette.alarm;
  if (status === "insufficient_data") return palette.caution;
  return palette.outline;
}

function cornersForDeck(corners: readonly (readonly [number, number])[]) {
  const [topLeft, topRight, bottomRight, bottomLeft] = corners.map(
    ([lng, lat]) => [lng, lat] as [number, number],
  );
  return [bottomLeft, topLeft, topRight, bottomRight] as [
    [number, number],
    [number, number],
    [number, number],
    [number, number],
  ];
}

function outlineRings(scene: SceneSummary | null): Ring[] {
  const outline = scene?.outline;
  if (!outline) return [];
  const polygons = outline.type === "Polygon" ? [outline.coordinates] : outline.coordinates;
  return polygons.map((polygon, index) => ({
    id: `footprint-${index}`,
    path: (polygon[0] ?? []).map(([lng, lat]) => [lng, lat] as [number, number]),
  }));
}

function sceneLayers(analysis: Analysis, showImage: boolean, showMask: boolean, opacity: number) {
  const layers: Layer[] = [];
  const { image, mask } = analysis.layers;
  if (showImage && image)
    layers.push(
      new BitmapLayer<Anchored>({
        id: `analysis:image:${analysis.id}`,
        ...UNDER_COASTLINE,
        image: analysisFileUrl(analysis.id, "image.png"),
        bounds: cornersForDeck(image.corners),
        opacity,
      }),
    );
  if (showMask && mask)
    layers.push(
      new BitmapLayer<Anchored>({
        id: `analysis:mask:${analysis.id}`,
        ...UNDER_COASTLINE,
        image: analysisFileUrl(analysis.id, "mask.png"),
        bounds: cornersForDeck(mask.corners),
        textureParameters: { minFilter: "nearest", magFilter: "nearest" },
      }),
    );
  return layers;
}

function areaLayers(analysis: Analysis, palette: MapPalette) {
  const ring: Ring = {
    id: analysis.id,
    path: (analysis.area.coordinates[0] ?? []).map(([lng, lat]) => [lng, lat]),
  };
  const zones = analysis.detection.zones.flatMap((zone) =>
    zone.geometry ? [{ type: "Feature" as const, geometry: zone.geometry, properties: zone }] : [],
  );
  const layers: Layer[] = [
    new PathLayer<Ring, PathStyleExtensionProps<Ring> & Anchored>({
      id: "analysis:area",
      ...UNDER_LABELS,
      data: [ring],
      getPath: (entry) => entry.path,
      getColor: statusColor(analysis.status.status, palette),
      getWidth: 1.6,
      widthUnits: "pixels",
      getDashArray: AREA_DASH,
      dashJustified: true,
      extensions: [new PathStyleExtension({ dash: true })],
      updateTriggers: { getColor: [analysis.status.status, palette.ground] },
    }),
  ];
  if (zones.length)
    layers.push(
      new GeoJsonLayer<Record<string, unknown>, Anchored>({
        id: "analysis:zones",
        ...UNDER_LABELS,
        data: zones,
        filled: true,
        stroked: true,
        getFillColor: withAlpha(palette.alarm, 0.3),
        getLineColor: palette.alarm,
        getLineWidth: 1.4,
        lineWidthUnits: "pixels",
        pointType: "circle",
        getPointRadius: 6,
        pointRadiusUnits: "pixels",
      }),
    );
  return layers;
}

function footprintLayers(scene: SceneSummary | null, palette: MapPalette) {
  const rings = outlineRings(scene);
  if (!rings.length) return [];
  return [
    new PathLayer<Ring, PathStyleExtensionProps<Ring> & Anchored>({
      id: "analysis:scene-footprint",
      ...UNDER_COASTLINE,
      data: rings,
      getPath: (entry) => entry.path,
      getColor: withAlpha(palette.outline, 0.72),
      getWidth: 1.3,
      widthUnits: "pixels",
      capRounded: true,
      getDashArray: FOOTPRINT_DASH,
      extensions: [new PathStyleExtension({ dash: true })],
      updateTriggers: { getColor: palette.ground },
    }),
  ];
}

type ObservationHandlers = {
  onHover: (info: PickingInfo<TimedObservation>) => void;
  onClick: (info: PickingInfo<TimedObservation>) => void;
};

function observationLayers(
  items: readonly TimedObservation[],
  hasReference: boolean,
  selectedId: string | null,
  palette: MapPalette,
  handlers: ObservationHandlers,
) {
  const ink = palette.outline;
  const faded = (item: TimedObservation) => hasReference && !item.inWindow;
  const segments: Segment[] = items.flatMap((item) =>
    item.feature.geometry.type === "LineString"
      ? [
          {
            id: item.feature.id,
            path: item.feature.geometry.coordinates.map(([lng, lat]) => [lng, lat]),
            faded: faded(item),
          },
        ]
      : [],
  );
  const selected = items.filter((item) => item.feature.id === selectedId);
  const layers: Layer[] = [];
  if (segments.length)
    layers.push(
      new PathLayer<Segment, Anchored>({
        id: "analysis:observation-segments",
        ...UNDER_LABELS,
        data: segments,
        getPath: (entry) => entry.path,
        getColor: (entry) => withAlpha(ink, entry.faded ? 0.35 : 0.8),
        getWidth: 2,
        widthUnits: "pixels",
        capRounded: true,
        updateTriggers: { getColor: [palette.ground, hasReference] },
      }),
    );
  layers.push(
    new ScatterplotLayer<TimedObservation, Anchored>({
      id: "analysis:observation-halo",
      ...UNDER_LABELS,
      data: items as TimedObservation[],
      getPosition: (item) => [item.point[0], item.point[1]],
      getRadius: (item) => markerRadius(item.feature.properties.concentration) + HALO_PX,
      radiusUnits: "pixels",
      getFillColor: palette.halo,
      updateTriggers: { getFillColor: palette.ground },
    }),
    new ScatterplotLayer<TimedObservation, Anchored>({
      id: "analysis:observations",
      ...UNDER_LABELS,
      data: items as TimedObservation[],
      pickable: true,
      getPosition: (item) => [item.point[0], item.point[1]],
      getRadius: (item) => markerRadius(item.feature.properties.concentration),
      radiusUnits: "pixels",
      stroked: true,
      filled: true,
      getFillColor: (item) =>
        item.feature.properties.concentration
          ? withAlpha(ink, faded(item) ? 0.35 : 0.92)
          : [0, 0, 0, 0],
      getLineColor: (item) => withAlpha(ink, faded(item) ? 0.5 : 1),
      getLineWidth: 1.4,
      lineWidthUnits: "pixels",
      updateTriggers: {
        getFillColor: [palette.ground, hasReference],
        getLineColor: [palette.ground, hasReference],
      },
      ...handlers,
    }),
    new TextLayer<TimedObservation, Anchored>({
      id: "analysis:observation-labels",
      ...UNDER_LABELS,
      data: items as TimedObservation[],
      getPosition: (item) => [item.point[0], item.point[1]],
      getText: (item) => labelText(item.feature.properties.concentration),
      getPixelOffset: (item) => [markerRadius(item.feature.properties.concentration) + 5, 0],
      getTextAnchor: "start",
      getAlignmentBaseline: "center",
      getSize: 12,
      getColor: (item) => withAlpha(ink, faded(item) ? 0.55 : 1),
      fontFamily: LABEL_FONT,
      fontWeight: 600,
      characterSet: LABEL_CHARACTERS,
      fontSettings: { sdf: true },
      outlineWidth: 3,
      outlineColor: palette.halo,
      updateTriggers: { getColor: [palette.ground, hasReference] },
    }),
  );
  if (selected.length)
    layers.push(
      new ScatterplotLayer<TimedObservation, Anchored>({
        id: "analysis:observation-selection",
        ...UNDER_LABELS,
        data: selected,
        getPosition: (item) => [item.point[0], item.point[1]],
        getRadius: (item) =>
          markerRadius(item.feature.properties.concentration) + SELECTION_RING_PX,
        radiusUnits: "pixels",
        filled: false,
        stroked: true,
        getLineColor: palette.selection,
        getLineWidth: 2.4,
        lineWidthUnits: "pixels",
      }),
    );
  return layers;
}

function hintFor(item: TimedObservation): string {
  const properties = item.feature.properties;
  return `${properties.sample_id} · ${formatConcentration(properties.concentration)} ${CONCENTRATION_UNIT} · ${formatDay(properties.date)} · ${profileLabel(properties.measurement_profile)} — щелчок: карточка`;
}

function useObservationHandlers(): ObservationHandlers {
  const map = useMainMap();
  const setHint = useStatusHintStore((state) => state.setHint);
  const selectObservation = useAnalysisStore((state) => state.selectObservation);
  const setPanelOpen = useAnalysisStore((state) => state.setPanelOpen);

  useEffect(
    () => () => {
      if (map) map.getCanvas().style.cursor = "";
    },
    [map],
  );

  const onHover = useCallback(
    (info: PickingInfo<TimedObservation>) => {
      const item = info.object;
      setHint(item ? hintFor(item) : null);
      if (map) map.getCanvas().style.cursor = item ? "pointer" : "";
    },
    [map, setHint],
  );
  const onClick = useCallback(
    (info: PickingInfo<TimedObservation>) => {
      const item = info.object;
      if (!item) return;
      selectObservation(item.feature.id);
      setPanelOpen(true);
    },
    [selectObservation, setPanelOpen],
  );
  return useMemo(() => ({ onHover, onClick }), [onHover, onClick]);
}

export function AnalysisLayers() {
  const demoActive = useDemoActive();
  const analysis = useCurrentAnalysis().data ?? null;
  const palette = useMapPalette();
  const composite = useMapLayersStore((state) => state.composite);
  const imageOpacity = useLayerOpacity("scene-true-color");
  const maskVisible = useLayerVisible("no-data");
  const areaVisible = useLayerVisible("analysis-area");
  const observationsVisible = useLayerVisible("field-observations");
  const footprintVisible = useLayerVisible("scene-footprint");
  const { scene, isDemo } = useSelectedScene();
  const view = useObservationsView();
  const selectedId = useAnalysisStore((state) => state.observationId);
  const handlers = useObservationHandlers();
  const hasReference = view.reference !== null;

  const layers = useMemo(() => {
    const list: Layer[] = [];
    if (!demoActive && analysis)
      list.push(
        ...sceneLayers(analysis, composite === "scene-true-color", maskVisible, imageOpacity),
      );
    if (!demoActive && !isDemo && footprintVisible) list.push(...footprintLayers(scene, palette));
    if (!demoActive && analysis && areaVisible) list.push(...areaLayers(analysis, palette));
    if (observationsVisible && view.onMap.length)
      list.push(...observationLayers(view.onMap, hasReference, selectedId, palette, handlers));
    return list;
  }, [
    demoActive,
    analysis,
    composite,
    maskVisible,
    imageOpacity,
    isDemo,
    footprintVisible,
    scene,
    palette,
    areaVisible,
    observationsVisible,
    view.onMap,
    hasReference,
    selectedId,
    handlers,
  ]);

  useDeckLayers("analysis:layers", layers);
  return null;
}
