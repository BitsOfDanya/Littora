"use client";

import { PathStyleExtension, type PathStyleExtensionProps } from "@deck.gl/extensions";
import { PathLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { useMemo } from "react";
import type { SurveyPort } from "@/data/survey";
import type { LngLat } from "@/domain/geo";
import { hexToRgba, type Rgba } from "@/features/map/color";
import { UNDER_COASTLINE } from "@/features/map/deck/anchors";
import { useDeckLayers } from "@/features/map/deck/use-deck-layers";
import { GROUND_INK } from "@/features/map/palette";
import { SURVEY } from "@/features/map/ramps";
import { useGround } from "@/features/map/use-map-palette";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { useLayerVisible } from "@/state/map-layers-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { circlePath, selectedTargetOf } from "./plan-model";
import { hhmm } from "./survey-copy";
import { useSurveyCamera } from "./use-survey-camera";
import { type SurveyView, useSurveyView } from "./use-survey-view";

type Path = { id: string; path: [number, number][] };
type Ring = { id: string; rank: number; position: [number, number] };

const toPath = (points: readonly LngLat[]): [number, number][] =>
  points.map(([lng, lat]) => [lng, lat]);

function cssToRgba(color: string): Rgba {
  const match = color.match(/rgba?\(([^)]+)\)/);
  if (!match) return hexToRgba(color);
  const [red, green, blue, alpha = "1"] = match[1].split(",").map((part) => part.trim());
  return [Number(red), Number(green), Number(blue), Math.round(Number(alpha) * 255)];
}

function useSurveyGeometry(view: SurveyView | null) {
  return useMemo(() => {
    if (!view) return null;
    const rankById = new Map(view.ranked.map((entry) => [entry.target.id, entry.rank]));
    const rings: Ring[] = view.plan.targets.map((target) => {
      const [lng, lat] = view.drift.get(target.id)?.position ?? target.observedPosition;
      return { id: target.id, rank: rankById.get(target.id) ?? 0, position: [lng, lat] };
    });
    const radii: Path[] = view.plan.targets.map((target) => {
      const state = view.drift.get(target.id);
      return {
        id: target.id,
        path: toPath(
          circlePath(
            state?.position ?? target.observedPosition,
            state?.radiusKm ?? target.searchRadius.baseKm,
          ),
        ),
      };
    });
    const links: Path[] = view.plan.targets.map((target) => ({
      id: target.id,
      path: toPath([
        target.observedPosition,
        view.drift.get(target.id)?.position ?? target.observedPosition,
      ]),
    }));
    const route: Path = { id: "route", path: toPath(view.route.path) };
    return { rings, radii, links, route };
  }, [view]);
}

function portLayers(
  port: SurveyPort,
  departure: string,
  paper: Rgba,
  mark: Rgba,
  label: string,
  halo: Rgba,
) {
  const position: [number, number] = [port.position[0], port.position[1]];
  return [
    new ScatterplotLayer<{ position: [number, number] }>({
      id: "survey:port",
      data: [{ position }],
      getPosition: (entry) => entry.position,
      getRadius: 5,
      radiusUnits: "pixels",
      stroked: true,
      getFillColor: paper,
      getLineColor: mark,
      getLineWidth: 2,
      lineWidthUnits: "pixels",
    }),
    new TextLayer<{ position: [number, number]; text: string }>({
      id: "survey:port-label",
      data: [{ position, text: `${port.name} · выход ${hhmm(departure)}` }],
      getPosition: (entry) => entry.position,
      getText: (entry) => entry.text,
      characterSet: "auto",
      getColor: hexToRgba(label),
      getSize: 12,
      getPixelOffset: [10, 0],
      getTextAnchor: "start",
      getAlignmentBaseline: "center",
      fontFamily: "IBM Plex Sans, sans-serif",
      outlineWidth: 3,
      outlineColor: halo,
      fontSettings: { sdf: true },
    }),
  ];
}

export function SurveyLayers() {
  const view = useSurveyView();
  const geometry = useSurveyGeometry(view);
  useSurveyCamera(view);
  const ground = useGround();
  const showTargets = useLayerVisible("survey-targets");
  const showRoute = useLayerVisible("survey-route");
  const showRadius = useLayerVisible("search-radius");
  const rawSelectedId = useWorkspaceStore((state) => state.selectedTargetId);
  const zoneId = useWorkspaceStore((state) => state.selectedCandidateId);
  const selectedId = view
    ? selectedTargetOf(view.plan.targets, rawSelectedId, zoneId)
    : rawSelectedId;
  const selectTarget = useWorkspaceStore((state) => state.selectTarget);
  const setHint = useStatusHintStore((state) => state.setHint);

  const layers = useMemo(() => {
    if (!geometry || !view) return [];
    const port = view.plan.port;
    const mark = hexToRgba(SURVEY.ink[ground].mark);
    const paper = hexToRgba(SURVEY.ink[ground].ringFill, 240);
    const ink = GROUND_INK[ground];
    const halo = cssToRgba(ink.halo);
    const linkInk = hexToRgba(ink.outline, 200);
    const result = [];
    if (showRadius) {
      result.push(
        new PathLayer<Path, PathStyleExtensionProps<Path>>({
          id: "survey:search-radius",
          data: geometry.radii,
          getPath: (entry) => entry.path,
          getColor: mark,
          getWidth: SURVEY.searchRadiusWidthPx,
          widthUnits: "pixels",
          getDashArray: [...SURVEY.searchRadiusDash],
          extensions: [new PathStyleExtension({ dash: true })],
          ...UNDER_COASTLINE,
        }),
      );
    }
    if (showRoute) {
      result.push(
        new PathLayer<Path>({
          id: "survey:route-halo",
          data: [geometry.route],
          getPath: (entry) => entry.path,
          getColor: halo,
          getWidth: SURVEY.routeWidthPx + SURVEY.routeHaloPx,
          widthUnits: "pixels",
          jointRounded: true,
          capRounded: true,
          ...UNDER_COASTLINE,
        }),
        new PathLayer<Path, PathStyleExtensionProps<Path>>({
          id: "survey:route",
          data: [geometry.route],
          getPath: (entry) => entry.path,
          getColor: mark,
          getWidth: SURVEY.routeWidthPx,
          widthUnits: "pixels",
          getDashArray: [...SURVEY.routeDash],
          extensions: [new PathStyleExtension({ dash: true })],
          ...UNDER_COASTLINE,
        }),
        ...(port ? portLayers(port, view.departure, paper, mark, ink.label, halo) : []),
      );
    }
    if (showTargets) {
      result.push(
        new PathLayer<Path, PathStyleExtensionProps<Path>>({
          id: "survey:links",
          data: geometry.links,
          getPath: (entry) => entry.path,
          getColor: linkInk,
          getWidth: 1.2,
          widthUnits: "pixels",
          getDashArray: [1, 3],
          extensions: [new PathStyleExtension({ dash: true })],
          ...UNDER_COASTLINE,
        }),
        new ScatterplotLayer<Ring>({
          id: "survey:targets",
          data: geometry.rings,
          pickable: true,
          getPosition: (ring) => ring.position,
          getRadius: SURVEY.ringRadiusPx,
          radiusUnits: "pixels",
          stroked: true,
          getFillColor: (ring) => (ring.id === selectedId ? mark : paper),
          getLineColor: mark,
          getLineWidth: SURVEY.ringWidthPx,
          lineWidthUnits: "pixels",
          updateTriggers: { getFillColor: [selectedId, ground] },
          onHover: (info) => {
            const ring = info.object as Ring | undefined;
            setHint(ring ? `Цель ${ring.rank} · ${ring.id} — щелчок: открыть в плане` : null);
          },
          onClick: (info) => {
            const ring = info.object as Ring | undefined;
            if (ring) selectTarget(ring.id);
          },
        }),
        new TextLayer<Ring>({
          id: "survey:ranks",
          data: geometry.rings,
          getPosition: (ring) => ring.position,
          getText: (ring) => String(ring.rank),
          getColor: (ring) => (ring.id === selectedId ? paper : mark),
          updateTriggers: { getColor: [selectedId, ground] },
          getSize: 12,
          fontFamily: "IBM Plex Mono, monospace",
          fontWeight: 600,
          getTextAnchor: "middle",
          getAlignmentBaseline: "center",
        }),
      );
    }
    return result;
  }, [
    geometry,
    view,
    ground,
    showTargets,
    showRoute,
    showRadius,
    selectedId,
    selectTarget,
    setHint,
  ]);

  useDeckLayers("survey", layers);
  return null;
}
