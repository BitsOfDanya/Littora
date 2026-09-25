"use client";

import type { Layer, PickingInfo } from "@deck.gl/core";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type PassCandidate, usePassCandidates } from "@/data/monitor-passes";
import { useSceneConditions } from "@/data/monitor-scene";
import { useDeckLayers } from "@/features/map/deck/use-deck-layers";
import { rampFor } from "@/features/map/ramps";
import { useMapViewStore } from "@/features/map/state/map-view-store";
import { useMainMap } from "@/features/map/use-main-map";
import { useGroundInk, useMapPalette } from "@/features/map/use-map-palette";
import { orderByPriority } from "@/features/objects/object-order";
import { usePrefersReducedMotion } from "@/features/shell/layout/use-environment";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { useSelectedScene } from "@/features/time-rail/use-selected-scene";
import { formatPercent } from "@/lib/format/numbers";
import { useLayerVisible } from "@/state/map-layers-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { LabelDemoChips, type LabelFeature, useCandidateLabelLayers } from "./candidate-labels";
import { aggregateHotspots, type HotspotCell } from "./hotspots";
import { candidateLabel, labelParts } from "./label-text";
import {
  candidateHitLayer,
  type CandidateFeature,
  candidateOutlineLayer,
  type CellDatum,
  coverageCellsLayer,
  footprintLayer,
  hotspotLayer,
  hoverLayer,
  type LayerMotion,
  noDataLayer,
  type NoDataDatum,
  type RingDatum,
  selectionLayers,
  uncertaintyLayer,
  type UncertaintyDatum,
} from "./layer-builders";

export const HOTSPOT_MAX_ZOOM = 9;
const FADE_MS = 150;
const IDLE_HINT = "Щелчок по пятну — открыть досье · J — следующее";
const NO_PASS: readonly PassCandidate[] = [];

function toFeature(entry: PassCandidate): CandidateFeature {
  return {
    type: "Feature",
    geometry: entry.geometry,
    properties: {
      id: entry.candidate.id,
      confidence: entry.candidate.confidence.class,
      coverage: entry.coverage.value,
    },
  };
}

function useMonitorVisibility() {
  return {
    noData: useLayerVisible("no-data"),
    coverage: useLayerVisible("coverage"),
    hotspots: useLayerVisible("hotspots"),
    uncertainty: useLayerVisible("uncertainty"),
    candidates: useLayerVisible("candidates"),
    footprint: useLayerVisible("scene-footprint"),
    labels: useLayerVisible("labels"),
  };
}

type HoverSource = "candidates" | "hit" | "hotspots";

function useHoverTracking(selectedId: string | null, enabled: boolean) {
  const map = useMainMap();
  const setHint = useStatusHintStore((state) => state.setHint);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const sourcesRef = useRef<Record<HoverSource, { id: string; hint: string } | null>>({
    candidates: null,
    hit: null,
    hotspots: null,
  });
  const selectedRef = useRef(selectedId);

  useEffect(() => {
    selectedRef.current = selectedId;
  }, [selectedId]);

  const report = useCallback(
    (source: HoverSource, entry: { id: string; hint: string } | null) => {
      sourcesRef.current[source] = entry;
      const { hit, candidates, hotspots } = sourcesRef.current;
      const active = hit ?? candidates ?? hotspots;
      setHoveredId((current) =>
        current === (active?.id ?? null) ? current : (active?.id ?? null),
      );
      setHint(active ? active.hint : selectedRef.current ? null : IDLE_HINT);
      if (map) map.getCanvas().style.cursor = active ? "pointer" : "";
    },
    [map, setHint],
  );

  useEffect(() => {
    if (enabled && useStatusHintStore.getState().hint === null && !selectedRef.current)
      setHint(IDLE_HINT);
  }, [enabled, setHint]);

  useEffect(
    () => () => {
      if (useStatusHintStore.getState().hint === IDLE_HINT || sourcesRef.current.hit) setHint(null);
      if (map) map.getCanvas().style.cursor = "";
    },
    [map, setHint],
  );

  useEffect(() => {
    if (selectedId && useStatusHintStore.getState().hint === IDLE_HINT) setHint(null);
  }, [selectedId, setHint]);

  return { hoveredId, report };
}

function useCandidateHandlers(report: ReturnType<typeof useHoverTracking>["report"]) {
  const selectCandidate = useWorkspaceStore((state) => state.selectCandidate);
  const featureHover = useCallback(
    (source: HoverSource) => (info: PickingInfo<CandidateFeature>) => {
      const id = info.object?.properties.id;
      report(source, id ? { id, hint: `${id} — щелчок: открыть досье` } : null);
    },
    [report],
  );
  const onClick = useCallback(
    (info: PickingInfo<CandidateFeature>) => {
      const id = info.object?.properties.id;
      if (id) selectCandidate(id);
    },
    [selectCandidate],
  );
  const onHotspotHover = useCallback(
    (info: PickingInfo<HotspotCell>) => {
      const cell = info.object;
      const id = cell?.candidateIds[0];
      report(
        "hotspots",
        cell && id
          ? {
              id,
              hint: `Ячейка 1 км · покрытие ${formatPercent(cell.coverage)} · ${id} — щелчок: открыть досье`,
            }
          : null,
      );
    },
    [report],
  );
  const onHotspotClick = useCallback(
    (info: PickingInfo<HotspotCell>) => {
      const id = info.object?.candidateIds[0];
      if (id) selectCandidate(id);
    },
    [selectCandidate],
  );
  return useMemo(
    () => ({
      outline: { onHover: featureHover("candidates"), onClick },
      hit: { onHover: featureHover("hit"), onClick },
      hotspot: { onHover: onHotspotHover, onClick: onHotspotClick },
    }),
    [featureHover, onClick, onHotspotHover, onHotspotClick],
  );
}

function footprintRing(polygon: GeoJSON.Polygon | undefined): RingDatum | null {
  const ring = polygon?.coordinates[0];
  return ring ? { id: "footprint", path: ring.map(([lng, lat]) => [lng, lat]) } : null;
}

export function MonitorLayers() {
  const map = useMainMap();
  const { scene } = useSelectedScene();
  const sceneId = scene?.id ?? null;
  const passSourced = usePassCandidates(sceneId);
  const conditionsSourced = useSceneConditions(sceneId);
  const pass = passSourced.origin === "none" ? NO_PASS : passSourced.data;
  const conditions = conditionsSourced.origin === "none" ? null : conditionsSourced.data;
  const isDemo = passSourced.origin === "demo";
  const palette = useMapPalette();
  const ink = useGroundInk();
  const ground = palette.ground;
  const ramp = rampFor("coverage", ground);
  const visible = useMonitorVisibility();
  const zoomedOut = useMapViewStore((state) => state.isReady && state.zoom < HOTSPOT_MAX_ZOOM);
  const reducedMotion = usePrefersReducedMotion();
  const selectedId = useWorkspaceStore((state) => state.selectedCandidateId);
  const { hoveredId, report } = useHoverTracking(selectedId, isDemo);
  const handlers = useCandidateHandlers(report);
  const motion: LayerMotion = useMemo(
    () => ({ fadeMs: reducedMotion ? 0 : FADE_MS }),
    [reducedMotion],
  );
  const showHotspots = visible.hotspots && zoomedOut;

  const features = useMemo(() => pass.map(toFeature), [pass]);
  const cells = useMemo<CellDatum[]>(
    () =>
      pass.flatMap((entry) =>
        entry.cells.map((cell) => ({
          polygon: cell.polygon,
          coverage: cell.coverage,
          candidateId: entry.candidate.id,
        })),
      ),
    [pass],
  );
  const hotspots = useMemo(
    () =>
      aggregateHotspots(
        pass.flatMap((entry) =>
          entry.cells.map((cell) => ({
            candidateId: entry.candidate.id,
            center: cell.center,
            coverage: cell.coverage,
          })),
        ),
      ),
    [pass],
  );
  const noData = useMemo<NoDataDatum[]>(
    () =>
      (conditions?.noData ?? []).map((area) => ({
        type: "Feature",
        geometry: area.polygon,
        properties: { kind: area.kind },
      })),
    [conditions],
  );
  const uncertainty = useMemo<UncertaintyDatum[]>(
    () =>
      (conditions?.uncertainty ?? []).map((area) => ({
        type: "Feature",
        geometry: area.polygon,
        properties: { uncertainty: area.uncertainty },
      })),
    [conditions],
  );
  const footprint = useMemo(() => footprintRing(conditions?.footprint), [conditions]);

  const baseLayers = useMemo(() => {
    const layers: Layer[] = [];
    if (visible.noData && noData.length) layers.push(noDataLayer(noData, ground, motion));
    if (visible.coverage && !showHotspots && cells.length)
      layers.push(coverageCellsLayer(cells, ramp, motion));
    if (showHotspots && hotspots.length)
      layers.push(
        hotspotLayer(hotspots, ramp, motion, handlers.hotspot.onHover, handlers.hotspot.onClick),
      );
    if (visible.uncertainty && uncertainty.length)
      layers.push(uncertaintyLayer(uncertainty, ground, motion));
    if (visible.candidates && !showHotspots && features.length)
      layers.push(candidateOutlineLayer(features, ground, palette, motion, handlers.outline));
    if ((visible.candidates || visible.coverage) && !showHotspots && features.length)
      layers.push(candidateHitLayer(features, handlers.hit));
    if (visible.footprint && footprint) layers.push(footprintLayer(footprint, palette));
    return layers;
  }, [
    visible,
    noData,
    cells,
    hotspots,
    uncertainty,
    features,
    footprint,
    ground,
    ramp,
    palette,
    motion,
    showHotspots,
    handlers,
  ]);

  const accentLayers = useMemo(() => {
    if (showHotspots) return [];
    const byId = (id: string | null) => features.find((feature) => feature.properties.id === id);
    const hovered = hoveredId !== selectedId ? byId(hoveredId) : undefined;
    const selected = byId(selectedId);
    return [
      ...(hovered ? [hoverLayer(hovered, palette)] : []),
      ...(selected ? selectionLayers(selected, palette) : []),
    ];
  }, [features, hoveredId, selectedId, palette, showHotspots]);

  const layers = useMemo(() => [...baseLayers, ...accentLayers], [baseLayers, accentLayers]);
  useDeckLayers("monitor:layers", layers);

  const rankOf = useMemo(() => {
    const ordered = orderByPriority(pass.map((entry) => entry.candidate));
    return new Map(ordered.map((candidate, index) => [candidate.id, index]));
  }, [pass]);

  const labelFeatures = useMemo<LabelFeature[]>(
    () =>
      pass.map((entry) => {
        const id = entry.candidate.id;
        const selected = id === selectedId;
        return {
          type: "Feature",
          geometry: { type: "Point", coordinates: [...entry.labelPoint] },
          properties: {
            id,
            text: candidateLabel(id, entry.coverage.value),
            ...labelParts(id, entry.coverage.value),
            rank: rankOf.get(id) ?? 99,
            active: selected || id === hoveredId,
            selected,
          },
        };
      }),
    [pass, selectedId, hoveredId, rankOf],
  );

  const labelsVisible = visible.labels && (visible.candidates || visible.coverage);
  useCandidateLabelLayers(map, { features: labelFeatures, visible: labelsVisible, ink });

  const chipTargets = useMemo(
    () =>
      isDemo && labelsVisible && !showHotspots
        ? pass
            .filter(
              (entry) => entry.candidate.id === selectedId || entry.candidate.id === hoveredId,
            )
            .map((entry) => ({ id: entry.candidate.id, point: entry.labelPoint }))
        : [],
    [isDemo, labelsVisible, showHotspots, pass, selectedId, hoveredId],
  );

  return <LabelDemoChips map={map} targets={chipTargets} />;
}
