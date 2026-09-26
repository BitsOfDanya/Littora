"use client";

import type { Layer } from "@deck.gl/core";
import { PathStyleExtension, type PathStyleExtensionProps } from "@deck.gl/extensions";
import { PathLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import type { MapMouseEvent, Map as MapLibreMap } from "maplibre-gl";
import { useEffect, useMemo } from "react";
import type { LngLat } from "@/domain/geo";
import { withAlpha } from "@/features/map/color";
import { useDeckLayers } from "@/features/map/deck/use-deck-layers";
import { useMapFurnitureVisible } from "@/features/map/furniture/use-furniture-visible";
import type { MapPalette } from "@/features/map/palette";
import { useMainMap } from "@/features/map/use-main-map";
import { useMapPalette } from "@/features/map/use-map-palette";
import { useHotkey } from "@/features/shell/hotkeys";
import { useEscapeLayer } from "@/features/shell/keyboard/escape-stack";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { useShellUiStore } from "@/state/shell-ui-store";
import {
  formatRulerDistance,
  type RulerSegment,
  rulerSegments,
  totalMeters,
} from "./ruler-geometry";
import { useRulerStore } from "./ruler-store";

type Position = [number, number];
type RulerPath = { id: string; path: Position[] };
type RulerVertex = { id: string; position: Position };
type RulerLabel = { id: string; position: Position; text: string; total: boolean };

const HINT_PREFIX = "Линейка:";
const SAME_POINT_PX = 4;
const DRAFT_DASH: [number, number] = [4, 3];
const LABEL_FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
const VERTEX_PX = 3.5;

function toPosition([lng, lat]: LngLat): Position {
  return [lng, lat];
}

function rulerHint(pointCount: number, finished: boolean, meters: number): string {
  const total = `всего ${formatRulerDistance(meters)}`;
  if (finished) return `${HINT_PREFIX} ${total} · щелчок — новое измерение, Esc — сбросить`;
  if (pointCount === 0) return `${HINT_PREFIX} щелчок — первая точка, Esc — выйти`;
  return `${HINT_PREFIX} щелчок — точка, двойной щелчок или Enter — конец, Esc — сбросить · ${total}`;
}

function rulerLabels(segments: readonly RulerSegment[], meters: number): RulerLabel[] {
  const end = segments.at(-1);
  if (!end) return [];
  const several = segments.length > 1;
  const labels: RulerLabel[] = several
    ? segments.map((entry, index) => ({
        id: `segment-${index}`,
        position: toPosition(entry.midpoint),
        text: formatRulerDistance(entry.meters),
        total: false,
      }))
    : [];
  labels.push({
    id: "total",
    position: toPosition(end.to),
    text: several ? `Σ ${formatRulerDistance(meters)}` : formatRulerDistance(meters),
    total: true,
  });
  return labels;
}

function rulerLayers(
  points: readonly LngLat[],
  segments: readonly RulerSegment[],
  meters: number,
  palette: MapPalette,
): Layer[] {
  const ink = palette.outline;
  const committed = segments.filter((entry) => !entry.draft);
  const draft = segments.filter((entry) => entry.draft);
  const line: RulerPath[] = committed.length
    ? [
        {
          id: "line",
          path: committed.flatMap((entry, index) =>
            (index === 0 ? entry.path : entry.path.slice(1)).map(toPosition),
          ),
        },
      ]
    : [];
  const drafts: RulerPath[] = draft.map((entry, index) => ({
    id: `draft-${index}`,
    path: entry.path.map(toPosition),
  }));
  const vertices: RulerVertex[] = points.map((point, index) => ({
    id: `vertex-${index}`,
    position: toPosition(point),
  }));
  return [
    new PathLayer<RulerPath>({
      id: "ruler:halo",
      data: line,
      getPath: (entry) => entry.path,
      getColor: palette.halo,
      getWidth: 4.5,
      widthUnits: "pixels",
      capRounded: true,
      jointRounded: true,
    }),
    new PathLayer<RulerPath>({
      id: "ruler:line",
      data: line,
      getPath: (entry) => entry.path,
      getColor: ink,
      getWidth: 1.75,
      widthUnits: "pixels",
      capRounded: true,
      jointRounded: true,
    }),
    new PathLayer<RulerPath, PathStyleExtensionProps<RulerPath>>({
      id: "ruler:draft",
      data: drafts,
      getPath: (entry) => entry.path,
      getColor: withAlpha(ink, 0.9),
      getWidth: 1.5,
      widthUnits: "pixels",
      getDashArray: DRAFT_DASH,
      extensions: [new PathStyleExtension({ dash: true })],
    }),
    new ScatterplotLayer<RulerVertex>({
      id: "ruler:vertices",
      data: vertices,
      getPosition: (entry) => entry.position,
      getRadius: VERTEX_PX,
      radiusUnits: "pixels",
      stroked: true,
      filled: true,
      getFillColor: palette.halo,
      getLineColor: ink,
      getLineWidth: 1.5,
      lineWidthUnits: "pixels",
    }),
    new TextLayer<RulerLabel>({
      id: "ruler:labels",
      data: rulerLabels(segments, meters),
      getPosition: (entry) => entry.position,
      getText: (entry) => entry.text,
      getTextAnchor: (entry) => (entry.total ? "start" : "middle"),
      getAlignmentBaseline: (entry) => (entry.total ? "center" : "bottom"),
      getPixelOffset: (entry) => (entry.total ? [VERTEX_PX + 8, 0] : [0, -6]),
      getSize: (entry) => (entry.total ? 13 : 11),
      getColor: ink,
      fontFamily: LABEL_FONT,
      fontWeight: 600,
      characterSet: "auto",
      fontSettings: { sdf: true },
      outlineWidth: 3,
      outlineColor: palette.halo,
    }),
  ];
}

function useRulerMapEvents(map: MapLibreMap | undefined): void {
  useEffect(() => {
    if (!map) return;
    const container = map.getCanvasContainer();
    const previousCursor = container.style.cursor;
    const zoomOnDoubleClick = map.doubleClickZoom.isEnabled();
    container.style.cursor = "crosshair";
    map.doubleClickZoom.disable();

    const handleClick = (event: MapMouseEvent) => {
      const { points, finished, addPoint } = useRulerStore.getState();
      const last = finished ? undefined : points.at(-1);
      if (last && map.project([last[0], last[1]]).dist(event.point) < SAME_POINT_PX) return;
      addPoint([event.lngLat.lng, event.lngLat.lat]);
    };
    const handleMove = (event: MapMouseEvent) => {
      const { points, finished, setCursor } = useRulerStore.getState();
      if (points.length && !finished) setCursor([event.lngLat.lng, event.lngLat.lat]);
    };
    const handleOut = () => useRulerStore.getState().setCursor(null);
    const handleDoubleClick = (event: MapMouseEvent) => {
      event.preventDefault();
      useRulerStore.getState().finish();
    };

    map.on("click", handleClick);
    map.on("mousemove", handleMove);
    map.on("mouseout", handleOut);
    map.on("dblclick", handleDoubleClick);
    return () => {
      map.off("click", handleClick);
      map.off("mousemove", handleMove);
      map.off("mouseout", handleOut);
      map.off("dblclick", handleDoubleClick);
      container.style.cursor = previousCursor;
      if (zoomOnDoubleClick) map.doubleClickZoom.enable();
    };
  }, [map]);
}

function useRulerHint(text: string): void {
  const hint = useStatusHintStore((state) => state.hint);
  const setHint = useStatusHintStore((state) => state.setHint);

  useEffect(() => {
    if (hint !== null && !hint.startsWith(HINT_PREFIX)) return;
    if (hint !== text) setHint(text);
  }, [hint, text, setHint]);

  useEffect(
    () => () => {
      const { hint: current, setHint: reset } = useStatusHintStore.getState();
      if (current?.startsWith(HINT_PREFIX)) reset(null);
    },
    [],
  );
}

function escapeRuler(): void {
  const { points, clear, deactivate } = useRulerStore.getState();
  if (points.length) clear();
  else deactivate();
}

function RulerSession() {
  const map = useMainMap();
  const palette = useMapPalette();
  const points = useRulerStore((state) => state.points);
  const cursor = useRulerStore((state) => state.cursor);
  const finished = useRulerStore((state) => state.finished);
  const finish = useRulerStore((state) => state.finish);
  const modalOpen = useShellUiStore((state) => state.shortcutSheetOpen);
  const segments = useMemo(
    () => rulerSegments(points, finished ? null : cursor),
    [points, cursor, finished],
  );
  const meters = totalMeters(segments);
  const layers = useMemo(
    () => rulerLayers(points, segments, meters, palette),
    [points, segments, meters, palette],
  );

  useRulerMapEvents(map);
  useRulerHint(rulerHint(points.length, finished, meters));
  useEscapeLayer(true, escapeRuler);
  useHotkey(["Enter", "NumpadEnter"], finish, {
    enabled: points.length > 0 && !finished && !modalOpen,
  });
  useDeckLayers("ruler:layers", layers);
  return null;
}

export function RulerLayer() {
  const active = useRulerStore((state) => state.active);
  const deactivate = useRulerStore((state) => state.deactivate);
  const available = useMapFurnitureVisible();

  useEffect(() => {
    if (!available) deactivate();
  }, [available, deactivate]);

  useEffect(() => () => useRulerStore.getState().deactivate(), []);

  return active && available ? <RulerSession /> : null;
}
