"use client";

import { TripsLayer } from "@deck.gl/geo-layers";
import { PathLayer } from "@deck.gl/layers";
import type { Map as MapLibreMap } from "maplibre-gl";
import { useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { type CurrentField, useCurrentField } from "@/data/forecast";
import { hexToRgba, withAlpha } from "@/features/map/color";
import { type Anchored, UNDER_LABELS } from "@/features/map/deck/anchors";
import { DRIFT, type Ground } from "@/features/map/ramps";
import { metersPerPixel } from "@/features/map/state/map-view-store";
import { useDeckLayerStore } from "@/features/map/state/deck-layer-store";
import { useMainMap } from "@/features/map/use-main-map";
import { useGround } from "@/features/map/use-map-palette";
import { useLayerVisible, useParticlesPaused } from "@/state/map-layers-store";
import {
  advanceBatch,
  type ParticleBatch,
  type ParticleTrip,
  PARTICLES,
  particleCount,
  seedParticles,
  seededRng,
  staticStreaks,
  timeScaleFor,
  type ViewBox,
} from "./particles";

const OWNER = "forecast:particles";
const LAYER_ID = "forecast:particles";
const WIDTH_PX = 1.4;
const SEED = 20_260_918;

type Frame = { width: number; height: number; view: ViewBox; scale: number };

function frameOf(map: MapLibreMap, field: CurrentField): Frame {
  const container = map.getContainer();
  const padding = map.getPadding();
  const left = padding.left ?? 0;
  const top = padding.top ?? 0;
  const right = container.clientWidth - (padding.right ?? 0);
  const bottom = container.clientHeight - (padding.bottom ?? 0);
  const corners = [
    map.unproject([left, top]),
    map.unproject([right, top]),
    map.unproject([left, bottom]),
    map.unproject([right, bottom]),
  ];
  const [fieldWest, fieldSouth, fieldEast, fieldNorth] = field.bounds;
  const view: ViewBox = {
    west: Math.max(fieldWest, Math.min(...corners.map((corner) => corner.lng))),
    east: Math.min(fieldEast, Math.max(...corners.map((corner) => corner.lng))),
    south: Math.max(fieldSouth, Math.min(...corners.map((corner) => corner.lat))),
    north: Math.min(fieldNorth, Math.max(...corners.map((corner) => corner.lat))),
  };
  const center = map.getCenter();
  return {
    width: Math.max(0, right - left),
    height: Math.max(0, bottom - top),
    view,
    scale: timeScaleFor(metersPerPixel(center.lat, map.getZoom()), field.typicalSpeedMs),
  };
}

function colorFor(ground: Ground) {
  const ink = DRIFT.ink[ground];
  return withAlpha(hexToRgba(ink.particle), Math.min(ink.particleAlpha, DRIFT.particleAlphaMax));
}

function tripsLayer(trips: readonly ParticleTrip[], currentTime: number, ground: Ground) {
  return new TripsLayer<ParticleTrip, Anchored>({
    id: LAYER_ID,
    ...UNDER_LABELS,
    data: trips,
    getPath: (trip) => trip.path,
    getTimestamps: (trip) => trip.timestamps,
    getColor: colorFor(ground),
    getWidth: WIDTH_PX,
    widthUnits: "pixels",
    capRounded: true,
    jointRounded: true,
    fadeTrail: true,
    trailLength: PARTICLES.trailSegments * PARTICLES.vertexStepS,
    currentTime,
    updateTriggers: { getColor: ground },
  });
}

function streaksLayer(streaks: readonly ParticleTrip[], ground: Ground) {
  return new PathLayer<ParticleTrip, Anchored>({
    id: LAYER_ID,
    ...UNDER_LABELS,
    data: streaks,
    getPath: (trip) => trip.path,
    getColor: colorFor(ground),
    getWidth: WIDTH_PX,
    widthUnits: "pixels",
    capRounded: true,
    jointRounded: true,
    updateTriggers: { getColor: ground },
  });
}

type ControllerState = { paused: boolean; ground: Ground; pageVisible: boolean };

type Controller = {
  update: (patch: Partial<ControllerState>) => void;
  dispose: () => void;
};

function createController(
  map: MapLibreMap,
  field: CurrentField,
  reducedMotion: boolean,
  initial: ControllerState,
): Controller {
  const { setGroup, removeGroup } = useDeckLayerStore.getState();
  const rng = seededRng(SEED);
  const state = { ...initial };
  let batch: ParticleBatch | null = null;
  let startedAt = 0;
  let frozenAt: number | null = null;
  let frame = 0;

  const running = () => !reducedMotion && !state.paused && state.pageVisible;

  const draw = (now: number) => {
    if (!batch) return;
    let elapsed = ((frozenAt ?? now) - startedAt) / 1_000;
    while (elapsed >= batch.duration) {
      const current = frameOf(map, field);
      const finished = batch.duration;
      batch = advanceBatch(field, current.view, batch.next, rng, current.scale);
      startedAt += finished * 1_000;
      elapsed -= finished;
    }
    setGroup(OWNER, [tripsLayer(batch.trips, elapsed, state.ground)]);
  };

  const tick = (now: number) => {
    frame = 0;
    draw(now);
    schedule();
  };

  const schedule = () => {
    if (running() && !frame) frame = requestAnimationFrame(tick);
  };

  const halt = () => {
    if (frame) cancelAnimationFrame(frame);
    frame = 0;
  };

  const freeze = (now: number) => {
    if (frozenAt === null) frozenAt = now;
  };

  const thaw = (now: number) => {
    if (frozenAt === null) return;
    startedAt += now - frozenAt;
    frozenAt = null;
  };

  const reseed = () => {
    const current = frameOf(map, field);
    const count = particleCount(current.width, current.height);
    if (reducedMotion) {
      setGroup(OWNER, [
        streaksLayer(staticStreaks(field, current.view, rng, count, current.scale), state.ground),
      ]);
      return;
    }
    const now = performance.now();
    batch = advanceBatch(
      field,
      current.view,
      seedParticles(field, current.view, rng, count),
      rng,
      current.scale,
    );
    startedAt = now;
    frozenAt = running() ? null : now;
    draw(now);
    schedule();
  };

  reseed();
  map.on("moveend", reseed);

  return {
    update: (patch) => {
      const groundChanged = patch.ground !== undefined && patch.ground !== state.ground;
      Object.assign(state, patch);
      const now = performance.now();
      if (running()) {
        thaw(now);
        schedule();
      } else {
        freeze(now);
        halt();
      }
      if (groundChanged) {
        if (reducedMotion) reseed();
        else draw(now);
      }
    },
    dispose: () => {
      halt();
      map.off("moveend", reseed);
      removeGroup(OWNER);
    },
  };
}

function usePageVisible(): boolean {
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    const update = () => setVisible(document.visibilityState === "visible");
    update();
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);
  return visible;
}

export function ParticlesLayer() {
  const map = useMainMap();
  const sourced = useCurrentField();
  const field = sourced.origin === "none" ? null : sourced.data;
  const visible = useLayerVisible("particles");
  const paused = useParticlesPaused();
  const reducedMotion = Boolean(useReducedMotion());
  const ground = useGround();
  const pageVisible = usePageVisible();
  const controllerRef = useRef<Controller | null>(null);
  const latestRef = useRef<ControllerState>({ paused, ground, pageVisible });

  useEffect(() => {
    latestRef.current = { paused, ground, pageVisible };
    controllerRef.current?.update({ paused, ground, pageVisible });
  }, [paused, ground, pageVisible]);

  useEffect(() => {
    if (!map || !field || !visible) return;
    const controller = createController(map, field, reducedMotion, latestRef.current);
    controllerRef.current = controller;
    return () => {
      controller.dispose();
      controllerRef.current = null;
    };
  }, [map, field, visible, reducedMotion]);

  return null;
}
