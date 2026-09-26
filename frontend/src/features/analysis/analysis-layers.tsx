"use client";

import type { Layer, PickingInfo } from "@deck.gl/core";
import { PathStyleExtension, type PathStyleExtensionProps } from "@deck.gl/extensions";
import { BitmapLayer, GeoJsonLayer, PathLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { CompositeLayerId } from "@/config/layers";
import type { SceneSummary } from "@/domain/scene";
import { useDemoActive } from "@/features/cartouche/use-layer-truth";
import { type Rgba, withAlpha } from "@/features/map/color";
import { useMapViewStore } from "@/features/map/state/map-view-store";
import { type Anchored, UNDER_COASTLINE, UNDER_LABELS } from "@/features/map/deck/anchors";
import { useDeckLayers } from "@/features/map/deck/use-deck-layers";
import type { MapPalette } from "@/features/map/palette";
import { useMainMap } from "@/features/map/use-main-map";
import { useMapPalette } from "@/features/map/use-map-palette";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { useSelectedScene } from "@/features/time-rail/use-selected-scene";
import {
  type Analysis,
  type AnalysisFile,
  analysisFileUrl,
  type ResultStatus,
} from "@/lib/api/analyses";
import { useAnalysisStore } from "@/state/analysis-store";
import { useLayerOpacity, useLayerVisible, useMapLayersStore } from "@/state/map-layers-store";
import { CONCENTRATION_UNIT, profileLabel } from "./analysis-copy";
import { formatConcentration, formatDay } from "./format";
import { formatArea } from "@/lib/format/numbers";
import {
  declutterLabels,
  formatProbability,
  type RealZone,
  toRealZones,
  zoneAdvice,
  zoneColor,
  zoneLabel,
} from "./zones";
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
const ZONE_FILL_ALPHA = 0.3;
const ZONE_MARKER_PX = 5;
const ZONE_LABEL_LIMIT = 25;
const ZONE_MARKERS_MAX_ZOOM = 14;
const ZONE_LABEL_CHARACTERS = "zone-0123456789,.· ";

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

const COMPOSITE_FILES: Record<
  CompositeLayerId,
  { key: keyof Analysis["layers"]; file: AnalysisFile }
> = {
  "scene-true-color": { key: "image", file: "image.png" },
  "scene-false-color": { key: "false_color", file: "layers/false_color.png" },
  "scene-fdi": { key: "fdi", file: "layers/fdi.png" },
  "scene-ndvi": { key: "ndvi", file: "layers/ndvi.png" },
};

function sceneLayers(
  analysis: Analysis,
  composite: CompositeLayerId | null,
  showMask: boolean,
  showProbability: boolean,
  showCoverage: boolean,
  opacity: number,
) {
  const layers: Layer[] = [];
  const { mask, probability, coverage } = analysis.layers;
  const chosen = composite ? COMPOSITE_FILES[composite] : null;
  const image = chosen ? (analysis.layers[chosen.key] ?? analysis.layers.image) : null;
  const file = chosen && analysis.layers[chosen.key] ? chosen.file : "image.png";
  if (chosen && image)
    layers.push(
      new BitmapLayer<Anchored>({
        id: `analysis:image:${analysis.id}:${file}`,
        ...UNDER_COASTLINE,
        image: analysisFileUrl(analysis.id, file),
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
  if (showProbability && probability)
    layers.push(
      new BitmapLayer<Anchored>({
        id: `analysis:probability:${analysis.id}`,
        ...UNDER_LABELS,
        image: analysisFileUrl(analysis.id, "probability.png"),
        bounds: cornersForDeck(probability.corners),
        textureParameters: { minFilter: "nearest", magFilter: "nearest" },
      }),
    );
  if (analysis.layers.anomalies)
    layers.push(
      new BitmapLayer<Anchored>({
        id: `analysis:anomalies:${analysis.id}`,
        ...UNDER_LABELS,
        image: analysisFileUrl(analysis.id, "layers/anomalies.png"),
        bounds: cornersForDeck(analysis.layers.anomalies.corners),
        textureParameters: { minFilter: "nearest", magFilter: "nearest" },
      }),
    );
  if (showCoverage && coverage)
    layers.push(
      new BitmapLayer<Anchored>({
        id: `analysis:coverage:${analysis.id}`,
        ...UNDER_LABELS,
        image: analysisFileUrl(analysis.id, "layers/coverage.png"),
        bounds: cornersForDeck(coverage.corners),
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
  return [
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
}

type ZoneFeature = GeoJSON.Feature<GeoJSON.Polygon | GeoJSON.MultiPolygon, { zone: RealZone }>;

type ZoneHandlers = {
  onHover: (info: PickingInfo<ZoneFeature | RealZone>) => void;
  onClick: (info: PickingInfo<ZoneFeature | RealZone>) => void;
};

type ZoneStyle = {
  palette: MapPalette;
  zoom: number;
  threshold: number | null;
  selectedId: string | null;
  hoveredId: string | null;
  showMarkers: boolean;
};

function zoneFeatures(zones: readonly RealZone[]): ZoneFeature[] {
  return zones.flatMap((zone) =>
    zone.geometry
      ? [{ type: "Feature" as const, geometry: zone.geometry, properties: { zone } }]
      : [],
  );
}

function zoneOutline(id: string, features: ZoneFeature[], color: Rgba, widthPx: number) {
  return new GeoJsonLayer<{ zone: RealZone }, Anchored>({
    id,
    ...UNDER_LABELS,
    data: features,
    filled: false,
    stroked: true,
    lineWidthUnits: "pixels",
    lineJointRounded: true,
    getLineColor: color,
    getLineWidth: widthPx,
  });
}

function zoneLayers(
  zones: readonly RealZone[],
  { palette, zoom, threshold, selectedId, hoveredId, showMarkers }: ZoneStyle,
  handlers: ZoneHandlers,
) {
  if (!zones.length) return [];
  const features = zoneFeatures(zones);
  const colorOf = (zone: RealZone) => zoneColor(zone.probabilityMax, threshold);
  const pinned = zones.filter((zone) => zone.centroid);
  const labelled = declutterLabels(pinned, zoom, [selectedId, hoveredId], ZONE_LABEL_LIMIT);
  const layers: Layer[] = [
    new GeoJsonLayer<{ zone: RealZone }, Anchored>({
      id: "analysis:zones",
      ...UNDER_LABELS,
      data: features,
      pickable: true,
      filled: true,
      stroked: true,
      getFillColor: (feature) =>
        zoneAdvice(feature.properties.zone).kind === "not_debris"
          ? withAlpha(palette.outline, 0.08)
          : withAlpha(colorOf(feature.properties.zone), ZONE_FILL_ALPHA),
      getLineColor: (feature) =>
        zoneAdvice(feature.properties.zone).kind === "not_debris"
          ? palette.outline
          : colorOf(feature.properties.zone),
      getLineWidth: 1.4,
      lineWidthUnits: "pixels",
      lineWidthMinPixels: 1,
      updateTriggers: {
        getFillColor: [threshold, palette.ground],
        getLineColor: [threshold, palette.ground],
      },
      ...handlers,
    }),
  ];
  if (showMarkers)
    layers.push(
      new ScatterplotLayer<RealZone, Anchored>({
        id: "analysis:zone-markers",
        ...UNDER_LABELS,
        data: pinned,
        pickable: true,
        getPosition: (zone) => [...(zone.centroid ?? [0, 0])],
        getRadius: ZONE_MARKER_PX,
        radiusUnits: "pixels",
        stroked: true,
        filled: true,
        getFillColor: (zone) => {
          const kind = zoneAdvice(zone).kind;
          if (kind === "not_debris") return withAlpha(palette.outline, 0);
          return withAlpha(colorOf(zone), kind === "recheck" ? 0.12 : 0.55);
        },
        getLineColor: (zone) =>
          zoneAdvice(zone).kind === "not_debris" ? palette.outline : colorOf(zone),
        getLineWidth: 1.6,
        lineWidthUnits: "pixels",
        updateTriggers: { getFillColor: threshold, getLineColor: threshold },
        ...handlers,
      }),
    );
  const hovered = features.filter(
    (feature) => feature.properties.zone.id === hoveredId && hoveredId !== selectedId,
  );
  const selected = features.filter((feature) => feature.properties.zone.id === selectedId);
  if (hovered.length) layers.push(zoneOutline("analysis:zone-hover", hovered, palette.hover, 2.2));
  if (selected.length)
    layers.push(
      zoneOutline("analysis:zone-selection-halo", selected, withAlpha(palette.halo, 0.75), 6),
      zoneOutline("analysis:zone-selection", selected, palette.selection, 2.6),
    );
  const selectedPin = pinned.filter((zone) => zone.id === selectedId);
  if (selectedPin.length)
    layers.push(
      new ScatterplotLayer<RealZone, Anchored>({
        id: "analysis:zone-selection-ring",
        ...UNDER_LABELS,
        data: selectedPin,
        getPosition: (zone) => [...(zone.centroid ?? [0, 0])],
        getRadius: ZONE_MARKER_PX + SELECTION_RING_PX,
        radiusUnits: "pixels",
        filled: false,
        stroked: true,
        getLineColor: palette.selection,
        getLineWidth: 2.4,
        lineWidthUnits: "pixels",
      }),
    );
  layers.push(
    new TextLayer<RealZone, Anchored>({
      id: "analysis:zone-labels",
      ...UNDER_LABELS,
      data: labelled,
      getPosition: (zone) => [...(zone.centroid ?? [0, 0])],
      getText: zoneLabel,
      getPixelOffset: [ZONE_MARKER_PX + 6, 0],
      getTextAnchor: "start",
      getAlignmentBaseline: "center",
      getSize: 12,
      getColor: (zone) => (zone.id === selectedId ? palette.selection : palette.outline),
      fontFamily: LABEL_FONT,
      fontWeight: 600,
      characterSet: ZONE_LABEL_CHARACTERS,
      fontSettings: { sdf: true },
      outlineWidth: 3,
      outlineColor: palette.halo,
      updateTriggers: { getColor: [selectedId, palette.ground] },
    }),
  );
  return layers;
}

function zoneHint(zone: RealZone): string {
  const area = zone.areaM2 === null ? "" : ` · ${formatArea(zone.areaM2)}`;
  return `${zone.id} · p макс. ${formatProbability(zone.probabilityMax)}${area} — щелчок: досье зоны`;
}

function zoneOf(info: PickingInfo<ZoneFeature | RealZone>): RealZone | null {
  const object = info.object;
  if (!object) return null;
  return "properties" in object ? object.properties.zone : object;
}

function useZoneHandlers(onHovered: (id: string | null) => void): ZoneHandlers {
  const map = useMainMap();
  const setHint = useStatusHintStore((state) => state.setHint);
  const selectZone = useAnalysisStore((state) => state.selectZone);
  const onHover = useCallback(
    (info: PickingInfo<ZoneFeature | RealZone>) => {
      const zone = zoneOf(info);
      onHovered(zone?.id ?? null);
      setHint(zone ? zoneHint(zone) : null);
      if (map) map.getCanvas().style.cursor = zone ? "pointer" : "";
    },
    [map, setHint, onHovered],
  );
  const onClick = useCallback(
    (info: PickingInfo<ZoneFeature | RealZone>) => {
      const zone = zoneOf(info);
      if (zone) selectZone(zone.id);
    },
    [selectZone],
  );
  return useMemo(() => ({ onHover, onClick }), [onHover, onClick]);
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
  const probabilityVisible = useLayerVisible("debris-probability");
  const coverageVisible = useLayerVisible("coverage");
  const zonesVisible = useLayerVisible("detector-zones");
  const observationsVisible = useLayerVisible("field-observations");
  const footprintVisible = useLayerVisible("scene-footprint");
  const { scene, isDemo } = useSelectedScene();
  const view = useObservationsView();
  const selectedId = useAnalysisStore((state) => state.observationId);
  const handlers = useObservationHandlers();
  const hasReference = view.reference !== null;
  const zoneId = useAnalysisStore((state) => state.zoneId);
  const [hoveredZone, setHoveredZone] = useState<string | null>(null);
  const zoneHandlers = useZoneHandlers(setHoveredZone);
  const labelZoom = useMapViewStore((state) => Math.round(state.zoom * 2) / 2);
  const showMarkers = labelZoom < ZONE_MARKERS_MAX_ZOOM;
  const zones = useMemo(() => (analysis ? toRealZones(analysis.detection.zones) : []), [analysis]);

  const layers = useMemo(() => {
    const list: Layer[] = [];
    if (!demoActive && analysis)
      list.push(
        ...sceneLayers(
          analysis,
          composite,
          maskVisible,
          probabilityVisible,
          coverageVisible,
          imageOpacity,
        ),
      );
    if (!demoActive && !isDemo && footprintVisible) list.push(...footprintLayers(scene, palette));
    if (!demoActive && analysis && areaVisible) list.push(...areaLayers(analysis, palette));
    if (!demoActive && analysis && zonesVisible)
      list.push(
        ...zoneLayers(
          zones,
          {
            palette,
            zoom: labelZoom,
            threshold: analysis.detection.threshold ?? null,
            selectedId: zoneId,
            hoveredId: hoveredZone,
            showMarkers,
          },
          zoneHandlers,
        ),
      );
    if (observationsVisible && view.onMap.length)
      list.push(...observationLayers(view.onMap, hasReference, selectedId, palette, handlers));
    return list;
  }, [
    demoActive,
    analysis,
    composite,
    maskVisible,
    probabilityVisible,
    coverageVisible,
    zonesVisible,
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
    zones,
    zoneId,
    hoveredZone,
    showMarkers,
    labelZoom,
    zoneHandlers,
  ]);

  useDeckLayers("analysis:layers", layers);
  return null;
}
