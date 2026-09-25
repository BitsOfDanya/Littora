"use client";

import {
  type CoverageCell,
  centerlineOfWindrow,
  coverageCells,
  DEMO_CANDIDATE_SHAPES,
  DEMO_CANDIDATES,
} from "@/demo/candidates";
import { DEMO_SCENES } from "@/demo/scenes";
import { DEMO_CANDIDATE_HISTORIES } from "@/demo/timeline";
import type { Sourced } from "@/domain/data-origin";
import type { DebrisCandidate } from "@/domain/detection";
import type { LngLat } from "@/domain/geo";
import type { Estimate } from "@/domain/measurement";
import { useDemoSourced } from "./use-sourced";

export type { CoverageCell } from "@/demo/candidates";

export type PassState = "found" | "not-found" | "cloudy" | "no-data";

export type PassObservation = {
  sceneId: string;
  observedAt: string;
  state: PassState;
  coverage: Estimate | null;
  areaM2: number | null;
};

export type PassCandidate = {
  candidate: DebrisCandidate;
  geometry: GeoJSON.Polygon;
  coverage: Estimate;
  areaM2: number;
  cells: readonly CoverageCell[];
  labelPoint: LngLat;
  isLatest: boolean;
};

export type ObservationTable = Readonly<Record<string, readonly PassObservation[]>>;

const OBSERVATIONS: ObservationTable = Object.fromEntries(
  DEMO_CANDIDATE_HISTORIES.map((history) => [
    history.candidateId,
    history.passes.map((pass) => ({
      sceneId: pass.sceneId,
      observedAt: pass.observedAt,
      state: pass.state,
      coverage: pass.coverage,
      areaM2: pass.areaM2,
    })),
  ]),
);

function easternmost(polygon: GeoJSON.Polygon): LngLat {
  const ring = polygon.coordinates[0] ?? [];
  const best = ring.reduce((winner, point) => (point[0] > winner[0] ? point : winner), ring[0]);
  return [best[0], best[1]];
}

function buildPass(sceneId: string): readonly PassCandidate[] {
  return DEMO_CANDIDATES.flatMap((candidate) => {
    const history = DEMO_CANDIDATE_HISTORIES.find((entry) => entry.candidateId === candidate.id);
    const pass = history?.passes.find((entry) => entry.sceneId === sceneId);
    const shape = DEMO_CANDIDATE_SHAPES[candidate.id];
    if (!shape || pass?.state !== "found" || !pass.coverage || !pass.geometry) return [];
    const isLatest = sceneId === candidate.sceneId;
    const centerline = isLatest ? shape.centerline : centerlineOfWindrow(pass.geometry);
    const areaM2 = pass.areaM2 ?? candidate.areaM2;
    const widthM = shape.widthM * Math.sqrt(Math.max(areaM2, 1) / Math.max(candidate.areaM2, 1));
    return [
      {
        candidate,
        geometry: pass.geometry,
        coverage: pass.coverage,
        areaM2,
        cells: coverageCells(centerline, widthM, pass.coverage.value, shape.serial),
        labelPoint: easternmost(pass.geometry),
        isLatest,
      },
    ];
  });
}

const PASS_CACHE = new Map<string, readonly PassCandidate[]>();

function passCandidates(sceneId: string): readonly PassCandidate[] {
  let cached = PASS_CACHE.get(sceneId);
  if (!cached) {
    cached = buildPass(sceneId);
    PASS_CACHE.set(sceneId, cached);
  }
  return cached;
}

const LATEST_SCENE_ID = DEMO_SCENES[DEMO_SCENES.length - 1]?.id ?? null;

export function usePassCandidates(sceneId: string | null): Sourced<readonly PassCandidate[]> {
  const sourced = useDemoSourced(LATEST_SCENE_ID);
  if (sourced.origin === "none") return sourced;
  const resolved = sceneId ?? sourced.data;
  return { origin: sourced.origin, data: resolved ? passCandidates(resolved) : [] };
}

export function useCandidateObservations(): Sourced<ObservationTable> {
  return useDemoSourced(OBSERVATIONS);
}
