"use client";

import type { LngLat } from "@/domain/geo";
import type { Estimate } from "@/domain/measurement";
import { DEMO_CANDIDATE_HISTORIES } from "@/demo/timeline";
import { useDemoSourced } from "./use-sourced";

export type PassState = "found" | "not-found" | "cloudy" | "no-data";

export type CandidatePass = {
  sceneId: string;
  observedAt: string;
  state: PassState;
  geometry: GeoJSON.Polygon | null;
  centroid: LngLat | null;
  areaM2: number | null;
  coverage: Estimate | null;
};

export type CandidateHistory = {
  candidateId: string;
  passes: readonly CandidatePass[];
};

export const TIMELINE_DEMO_SOURCE = "src/demo/timeline.ts";

export const useCandidateHistories = () => useDemoSourced(DEMO_CANDIDATE_HISTORIES);
