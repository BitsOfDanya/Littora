"use client";

import type { Layer, PickingInfo } from "@deck.gl/core";
import { PathStyleExtension, type PathStyleExtensionProps } from "@deck.gl/extensions";
import { PathLayer, PolygonLayer, ScatterplotLayer } from "@deck.gl/layers";
import { useReducedMotion } from "motion/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { BeachSegmentRisk, DriftForecastDetail } from "@/data/forecast";
import type { DriftEnvelope, ForecastHorizonH } from "@/domain/forecast";
import type { LngLat } from "@/domain/geo";
import { hexToRgba, type Rgba, withAlpha } from "@/features/map/color";
import { type Anchored, UNDER_COASTLINE } from "@/features/map/deck/anchors";
import { useDeckLayers } from "@/features/map/deck/use-deck-layers";
import { GROUND_INK } from "@/features/map/palette";
import { BEACHING, DRIFT, type Ground } from "@/features/map/ramps";
import { useMainMap } from "@/features/map/use-main-map";
import { useGround } from "@/features/map/use-map-palette";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { useLayerVisible } from "@/state/map-layers-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { horizonLabel } from "./drift-math";
import { beachingHint, envelopeHint, hindcastText, horizonHint } from "./forecast-copy";
import { chooseHorizon as selectHorizon } from "./forecast-hotkeys";
import { type ForecastLabel, useForecastLabelLayers } from "./forecast-labels";
import { useSelectedForecast } from "./use-selected-forecast";

const FADE_MS = 150;
const ENVELOPE_DASH: [number, number] = [4, 3];
const ACTIVE_WIDTH_PX = 2;
const IDLE_WIDTH_PX = 1;
const MEDIAN_WIDTH_PX = 1.6;
const HINDCAST_WIDTH_PX = 2;
const RING_RADIUS_PX = 4;
const ACTIVE_RING_RADIUS_PX = 5.5;

type Path = { id: string; path: [number, number][] };
type Ring = { horizonH: ForecastHorizonH; position: LngLat };
type Segment = { risk: BeachSegmentRisk; path: [number, number][] };

type Visibility = {
  envelopes: boolean;
  median: boolean;
  hindcast: boolean;
  beaching: boolean;
};

type Style = {
  ground: Ground;
  horizonH: ForecastHorizonH;
  fadeMs: number;
};

type Handlers = {
  onHover: (info: PickingInfo) => void;
  onClick: (info: PickingInfo) => void;
};

function fadeIn(durationMs: number) {
  return { duration: durationMs, enter: (value: number[]) => [value[0], value[1], value[2], 0] };
}

function toPath(points: readonly LngLat[]): [number, number][] {
  return points.map(([lng, lat]) => [lng, lat]);
}

function envelopesLayer(
  forecast: DriftForecastDetail,
  { ground, horizonH, fadeMs }: Style,
  handlers: Handlers,
) {
  const ink = hexToRgba(DRIFT.ink[ground].envelope);
  const data = [...forecast.envelopes].sort((a, b) => b.horizonH - a.horizonH);
  return new PolygonLayer<DriftEnvelope, PathStyleExtensionProps<DriftEnvelope> & Anchored>({
    id: "forecast:envelopes",
    ...UNDER_COASTLINE,
    data,
    pickable: true,
    getPolygon: (envelope) => envelope.polygon.coordinates[0] as [number, number][],
    getFillColor: (envelope) => withAlpha(ink, DRIFT.envelopeFillAlpha[envelope.horizonH]),
    getLineColor: (envelope) => withAlpha(ink, envelope.horizonH === horizonH ? 1 : 0.62),
    getLineWidth: (envelope) => (envelope.horizonH === horizonH ? ACTIVE_WIDTH_PX : IDLE_WIDTH_PX),
    lineWidthUnits: "pixels",
    getDashArray: ENVELOPE_DASH,
    dashJustified: true,
    extensions: [new PathStyleExtension({ dash: true })],
    updateTriggers: { getLineColor: horizonH, getLineWidth: horizonH },
    transitions: { getFillColor: fadeIn(fadeMs), getLineColor: fadeIn(fadeMs) },
    ...handlers,
  });
}

function medianLayers(
  forecast: DriftForecastDetail,
  { ground, horizonH, fadeMs }: Style,
  handlers: Handlers,
) {
  const inkHex = DRIFT.ink[ground].median;
  const groundInk = GROUND_INK[ground];
  const ink = hexToRgba(inkHex, 240);
  const selection = hexToRgba(groundInk.selection);
  const halo = hexToRgba(ground === "dark" ? "#0A0E11" : "#FFFFFF", 235);
  const rings: Ring[] = forecast.envelopes.map((envelope) => ({
    horizonH: envelope.horizonH,
    position: envelope.median,
  }));
  return [
    new PathLayer<Path, PathStyleExtensionProps<Path> & Anchored>({
      id: "forecast:median",
      ...UNDER_COASTLINE,
      data: [{ id: "median", path: toPath(forecast.medianPath) }],
      getPath: (entry) => entry.path,
      getColor: ink,
      getWidth: MEDIAN_WIDTH_PX,
      widthUnits: "pixels",
      jointRounded: true,
      getDashArray: [...DRIFT.medianDash],
      dashJustified: true,
      extensions: [new PathStyleExtension({ dash: true })],
      transitions: { getColor: fadeIn(fadeMs) },
    }),
    new ScatterplotLayer<Ring, Anchored>({
      id: "forecast:horizon-rings",
      ...UNDER_COASTLINE,
      data: rings,
      pickable: true,
      getPosition: (ring) => [ring.position[0], ring.position[1]],
      getRadius: (ring) => (ring.horizonH === horizonH ? ACTIVE_RING_RADIUS_PX : RING_RADIUS_PX),
      radiusUnits: "pixels",
      stroked: true,
      filled: true,
      getFillColor: halo,
      getLineColor: (ring) => (ring.horizonH === horizonH ? selection : ink),
      getLineWidth: (ring) => (ring.horizonH === horizonH ? 2 : 1.4),
      lineWidthUnits: "pixels",
      updateTriggers: {
        getRadius: horizonH,
        getLineColor: [horizonH, ground],
        getLineWidth: horizonH,
      },
      transitions: { getFillColor: fadeIn(fadeMs), getLineColor: fadeIn(fadeMs) },
      ...handlers,
    }),
  ];
}

function hindcastLayers(forecast: DriftForecastDetail, { ground, fadeMs }: Style) {
  const ink = hexToRgba(DRIFT.ink[ground].median, 230);
  const halo = hexToRgba(ground === "dark" ? "#0A0E11" : "#FFFFFF", 235);
  const start = forecast.hindcastPath[0];
  return [
    new PathLayer<Path, PathStyleExtensionProps<Path> & Anchored>({
      id: "forecast:hindcast",
      ...UNDER_COASTLINE,
      data: [{ id: "hindcast", path: toPath(forecast.hindcastPath) }],
      getPath: (entry) => entry.path,
      getColor: ink,
      getWidth: HINDCAST_WIDTH_PX,
      widthUnits: "pixels",
      capRounded: true,
      jointRounded: true,
      getDashArray: [...DRIFT.hindcastDash],
      extensions: [new PathStyleExtension({ dash: true })],
      transitions: { getColor: fadeIn(fadeMs) },
    }),
    new ScatterplotLayer<{ position: LngLat }, Anchored>({
      id: "forecast:hindcast-start",
      ...UNDER_COASTLINE,
      data: [{ position: start }],
      getPosition: (entry) => [entry.position[0], entry.position[1]],
      getRadius: 3.5,
      radiusUnits: "pixels",
      stroked: true,
      filled: true,
      getFillColor: halo,
      getLineColor: ink,
      getLineWidth: 1.4,
      lineWidthUnits: "pixels",
      transitions: { getLineColor: fadeIn(fadeMs) },
    }),
  ];
}

function beachingLayers(
  forecast: DriftForecastDetail,
  { ground, fadeMs }: Style,
  handlers: Handlers,
) {
  const ink = BEACHING.ink[ground];
  const data: Segment[] = forecast.beaching
    .filter((risk) => risk.severity !== "info" && risk.path.length > 1)
    .map((risk) => ({ risk, path: toPath(risk.path) }))
    .reverse();
  if (!data.length) return [];
  const colorOf = (segment: Segment): Rgba =>
    hexToRgba(segment.risk.severity === "alarm" ? ink.alarm : ink.caution);
  const halo = ground === "dark" ? withAlpha(hexToRgba("#05080A"), 0.8) : hexToRgba(ink.halo);
  return [
    new PathLayer<Segment, Anchored>({
      id: "forecast:beaching-halo",
      ...UNDER_COASTLINE,
      data,
      getPath: (segment) => segment.path,
      getColor: halo,
      getWidth: BEACHING.haloPx,
      widthUnits: "pixels",
      capRounded: true,
      jointRounded: true,
      transitions: { getColor: fadeIn(fadeMs) },
    }),
    new PathLayer<Segment, Anchored>({
      id: "forecast:beaching",
      ...UNDER_COASTLINE,
      data,
      pickable: true,
      getPath: (segment) => segment.path,
      getColor: colorOf,
      getWidth: BEACHING.widthPx,
      widthUnits: "pixels",
      capRounded: true,
      jointRounded: true,
      updateTriggers: { getColor: ground },
      transitions: { getColor: fadeIn(fadeMs) },
      ...handlers,
    }),
  ];
}

function lowerFirst(text: string): string {
  return text.charAt(0).toLocaleLowerCase("ru") + text.slice(1);
}

export function buildForecastLabels(
  forecast: DriftForecastDetail,
  horizonH: ForecastHorizonH,
  show: Visibility,
): ForecastLabel[] {
  const labels: ForecastLabel[] = [];
  if (show.beaching) {
    forecast.beaching
      .filter((risk) => risk.severity !== "info" && risk.labelAt)
      .forEach((risk, index) =>
        labels.push({
          id: `beach-${risk.id}`,
          kind: "beach",
          text: `${risk.name} · ${risk.probability.value.toFixed(2).replace(".", ",")}`,
          position: risk.labelAt as LngLat,
          rank: index,
          severity: risk.severity === "alarm" ? "alarm" : "caution",
        }),
      );
  }
  if (show.hindcast) {
    labels.push({
      id: "hindcast",
      kind: "hindcast",
      text: hindcastText(forecast, lowerFirst),
      position: forecast.hindcastPath[0],
      rank: 10,
    });
  }
  if (show.median) {
    forecast.envelopes.forEach((envelope) =>
      labels.push({
        id: `horizon-${envelope.horizonH}`,
        kind: envelope.horizonH === horizonH ? "horizon-active" : "horizon",
        text: horizonLabel(envelope.horizonH),
        position: envelope.median,
        rank: envelope.horizonH === horizonH ? 20 : 30 + envelope.horizonH,
      }),
    );
  }
  return labels;
}

type HoverTarget =
  | { kind: "envelope"; envelope: DriftEnvelope }
  | { kind: "ring"; horizonH: ForecastHorizonH }
  | { kind: "beach"; risk: BeachSegmentRisk };

function hoverTargetOf(info: PickingInfo): HoverTarget | null {
  const object = info.object as unknown;
  if (!object || typeof object !== "object") return null;
  if (info.layer?.id === "forecast:envelopes")
    return { kind: "envelope", envelope: object as DriftEnvelope };
  if (info.layer?.id === "forecast:horizon-rings")
    return { kind: "ring", horizonH: (object as Ring).horizonH };
  if (info.layer?.id === "forecast:beaching")
    return { kind: "beach", risk: (object as Segment).risk };
  return null;
}

function useForecastHover(forecast: DriftForecastDetail | null) {
  const map = useMainMap();
  const setHint = useStatusHintStore((state) => state.setHint);
  const [hovered, setHovered] = useState(false);

  const onHover = useCallback(
    (info: PickingInfo) => {
      const target = forecast ? hoverTargetOf(info) : null;
      setHovered(Boolean(target));
      if (map) map.getCanvas().style.cursor = target ? "pointer" : "";
      if (!target || !forecast) {
        setHint(null);
        return;
      }
      if (target.kind === "envelope") setHint(envelopeHint(target.envelope));
      else if (target.kind === "ring") setHint(horizonHint(forecast, target.horizonH));
      else setHint(beachingHint(target.risk));
    },
    [forecast, map, setHint],
  );

  const onClick = useCallback((info: PickingInfo) => {
    const target = hoverTargetOf(info);
    if (target?.kind === "envelope") selectHorizon(target.envelope.horizonH);
    if (target?.kind === "ring") selectHorizon(target.horizonH);
  }, []);

  useEffect(
    () => () => {
      if (!hovered) return;
      setHint(null);
      if (map) map.getCanvas().style.cursor = "";
    },
    [hovered, map, setHint],
  );

  return useMemo(() => ({ onHover, onClick }), [onHover, onClick]);
}

export function ForecastLayers() {
  const map = useMainMap();
  const ground = useGround();
  const reducedMotion = Boolean(useReducedMotion());
  const selected = useSelectedForecast();
  const horizonH = useWorkspaceStore((state) => state.forecastHorizonH);
  const envelopes = useLayerVisible("forecast-envelopes");
  const median = useLayerVisible("forecast-median");
  const hindcast = useLayerVisible("forecast-hindcast");
  const beaching = useLayerVisible("beaching");
  const forecast = selected.status === "ready" ? selected.forecast : null;
  const handlers = useForecastHover(forecast);

  const show = useMemo(
    () => ({ envelopes, median, hindcast, beaching }),
    [envelopes, median, hindcast, beaching],
  );

  const layers = useMemo<Layer[]>(() => {
    if (!forecast) return [];
    const style: Style = { ground, horizonH, fadeMs: reducedMotion ? 0 : FADE_MS };
    return [
      ...(show.envelopes ? [envelopesLayer(forecast, style, handlers)] : []),
      ...(show.median ? medianLayers(forecast, style, handlers) : []),
      ...(show.hindcast ? hindcastLayers(forecast, style) : []),
      ...(show.beaching ? beachingLayers(forecast, style, handlers) : []),
    ];
  }, [forecast, ground, horizonH, reducedMotion, show, handlers]);

  const labels = useMemo(
    () => (forecast ? buildForecastLabels(forecast, horizonH, show) : []),
    [forecast, horizonH, show],
  );

  useDeckLayers("forecast", layers);
  useForecastLabelLayers(map, { labels, ground, ink: GROUND_INK[ground] });
  return null;
}
