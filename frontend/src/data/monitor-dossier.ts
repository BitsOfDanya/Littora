"use client";

import {
  type ConfuserRow,
  confusersFor,
  DEMO_CANDIDATE_SHAPES,
  DEMO_CANDIDATES,
  DEMO_RIVER_MOUTH,
  journalFor,
  type JournalFixtureRow,
} from "@/demo/candidates";
import { nearestNoDataM } from "@/demo/masks";
import { DEMO_REFERENCE_SPECTRA, referenceAtCoverage } from "@/demo/references";
import { findDemoScene } from "@/demo/scenes";
import { mixedPixelSpread } from "@/demo/spectra";
import type { Sourced } from "@/domain/data-origin";
import type { BandReflectance, DebrisCandidate } from "@/domain/detection";
import type { SceneSummary } from "@/domain/scene";
import { toLocalMeters } from "@/lib/geo/local-metric";
import { useDemoSourced } from "./use-sourced";

export type { ConfuserLikelihood, ConfuserRow, JournalFixtureRow } from "@/demo/candidates";
export type { ReferenceSpectrumKey } from "@/demo/references";

export type ReferenceSeries = {
  key: "plastic" | "sargassum" | "foam" | "water";
  label: string;
  source: string;
  bands: readonly BandReflectance[];
};

export type DossierData = {
  candidate: DebrisCandidate;
  scene: SceneSummary | undefined;
  areaInterval: readonly [number, number];
  uncertainty: number;
  sigma: readonly BandReflectance[];
  references: readonly ReferenceSeries[];
  confusers: readonly ConfuserRow[];
  journal: readonly JournalFixtureRow[];
  cloudOverSpot: number;
  nearestCloudM: number | null;
  mouth: { name: string; distanceM: number };
};

function distanceM(a: readonly [number, number], b: readonly [number, number]): number {
  const [x, y] = toLocalMeters(a, b);
  return Math.hypot(x, y);
}

function buildDossier(candidate: DebrisCandidate): DossierData | null {
  const shape = DEMO_CANDIDATE_SHAPES[candidate.id];
  if (!shape) return null;
  const scene = findDemoScene(candidate.sceneId);
  const nearestCloudM = nearestNoDataM(candidate.sceneId, candidate.centroid);
  const cloudOverSpot = nearestCloudM === 0 ? (scene?.cloudCover ?? 1) : 0;
  return {
    candidate,
    scene,
    areaInterval: shape.areaInterval,
    uncertainty: shape.uncertainty,
    sigma: mixedPixelSpread(candidate.coverage, shape.turbidity),
    references: DEMO_REFERENCE_SPECTRA.map((reference) => ({
      key: reference.key,
      label: reference.label,
      source: reference.source,
      bands: referenceAtCoverage(reference, candidate.coverage.value, shape.turbidity),
    })),
    confusers: confusersFor(candidate, shape, { scene, nearestCloudM, cloudOverSpot }),
    journal: journalFor(candidate),
    cloudOverSpot,
    nearestCloudM,
    mouth: {
      name: DEMO_RIVER_MOUTH.name,
      distanceM: Math.round(distanceM(candidate.centroid, DEMO_RIVER_MOUTH.position)),
    },
  };
}

const DOSSIERS: Readonly<Record<string, DossierData | null>> = Object.fromEntries(
  DEMO_CANDIDATES.map((candidate) => [candidate.id, buildDossier(candidate)]),
);

export function useCandidateDossier(candidateId: string | null): Sourced<DossierData | null> {
  const sourced = useDemoSourced(DOSSIERS);
  if (sourced.origin === "none") return sourced;
  return {
    origin: sourced.origin,
    data: candidateId ? (sourced.data[candidateId] ?? null) : null,
  };
}
