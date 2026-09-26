"use client";

import { useMutation, useMutationState, useQuery, useQueryClient } from "@tanstack/react-query";
import { DEMO_CANDIDATES } from "@/demo/candidates";
import {
  DEMO_CURRENT_FIELD,
  DEMO_FORECAST_DETAILS,
  DEMO_FORECAST_RUN,
  DEMO_FORECASTS,
} from "@/demo/forecast";
import type { Sourced } from "@/domain/data-origin";
import type { DriftForecast } from "@/domain/forecast";
import type { LngLat } from "@/domain/geo";
import { type Analysis, getAnalysis } from "@/lib/api/analyses";
import { createDrift, getDrift } from "@/lib/api/drift";
import { ApiError } from "@/lib/api/errors";
import { getMeta } from "@/lib/api/system";
import { queryKeys } from "@/lib/query/query-keys";
import { useAnalysisStore } from "@/state/analysis-store";
import {
  type DriftCandidate,
  type DriftInputs,
  type DriftScenario,
  type DriftState,
  driftStateOf,
  toDriftCandidates,
  toDriftScenario,
} from "./drift";
import { useDemoSourced } from "./use-sourced";

export type Velocity = readonly [eastMs: number, northMs: number];

export type CurrentField = {
  label: string;
  bounds: readonly [west: number, south: number, east: number, north: number];
  typicalSpeedMs: number;
  velocityAt: (lng: number, lat: number) => Velocity | null;
  isWater: (lng: number, lat: number) => boolean;
};

export type ProbabilityEstimate = { value: number; low: number; high: number };

export type BeachingSeverity = "alarm" | "caution" | "info";

export type BeachSegmentRisk = {
  id: string;
  name: string;
  severity: BeachingSeverity;
  probability: ProbabilityEstimate;
  members: number;
  windowH: readonly [from: number, to: number];
  path: readonly LngLat[];
  labelAt: LngLat | null;
};

export type SourceEstimate = {
  id: string;
  name: string;
  position: LngLat | null;
  probability: ProbabilityEstimate;
  members: number;
};

export type ForecastRun = {
  t0: string;
  runAt: string;
  issuedAt: string;
  ensembleSize: number;
  windageRatio: number;
  windFromDeg: number;
  windSpeedMs: number;
  hindcastHours: number;
  currents: string;
  wind: string;
  model: string;
};

export type DriftForecastDetail = DriftForecast & {
  origin: LngLat;
  hindcastPath: readonly LngLat[];
  beachedByHour: readonly number[];
  beaching: readonly BeachSegmentRisk[];
  beachingAny: ProbabilityEstimate;
  sources: readonly SourceEstimate[];
};

export const HINDCAST_HOURS = 48;

const META_STALE_MS = 5 * 60_000;
const COMPUTE_KEY = ["drift", "compute"] as const;
const NO_CANDIDATES: readonly DriftCandidate[] = [];

type DriftSource = { state: DriftState; candidates: readonly DriftCandidate[] };

const selectCandidates = (analysis: Analysis) => toDriftCandidates(analysis.detection.zones);

async function loadDrift(analysisId: string, signal: AbortSignal): Promise<DriftScenario | null> {
  try {
    return toDriftScenario(await getDrift(analysisId, signal));
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

function useDriftCapable(): boolean {
  const meta = useQuery({
    queryKey: queryKeys.system.meta,
    queryFn: ({ signal }) => getMeta(signal),
    staleTime: META_STALE_MS,
  });
  return (
    meta.data?.capabilities.some(
      (capability) => capability.key === "drift_forecast" && capability.status === "available",
    ) ?? false
  );
}

export function useComputeDrift() {
  const client = useQueryClient();
  return useMutation({
    mutationKey: COMPUTE_KEY,
    mutationFn: (analysisId: string) => createDrift(analysisId).then(toDriftScenario),
    onSuccess: (scenario, analysisId) =>
      client.setQueryData(queryKeys.analyses.drift(analysisId), scenario),
  }).mutate;
}

function useLatestCompute(analysisId: string | null): DriftInputs["compute"] {
  const runs = useMutationState({
    filters: { mutationKey: COMPUTE_KEY },
    select: (mutation) => ({
      analysisId: mutation.state.variables,
      status: mutation.state.status,
      error: mutation.state.error,
    }),
  });
  for (let index = runs.length - 1; index >= 0; index -= 1)
    if (runs[index].analysisId === analysisId) return runs[index];
  return null;
}

function useDriftSource(): DriftSource {
  const live = useDemoSourced(DEMO_FORECAST_RUN).origin !== "demo";
  const capable = useDriftCapable();
  const analysisId = useAnalysisStore((state) => state.analysisId);
  const active = live && capable && analysisId !== null;
  const analysis = useQuery({
    queryKey: queryKeys.analyses.detail(analysisId ?? ""),
    queryFn: ({ signal }) => getAnalysis(analysisId ?? "", signal),
    enabled: active,
    staleTime: Infinity,
    select: selectCandidates,
  });
  const candidates = (active && analysis.data) || NO_CANDIDATES;
  const drift = useQuery({
    queryKey: queryKeys.analyses.drift(analysisId ?? ""),
    queryFn: ({ signal }) => loadDrift(analysisId ?? "", signal),
    enabled: active && candidates.length > 0,
    staleTime: Infinity,
  });
  const compute = useComputeDrift();
  const latest = useLatestCompute(analysisId);
  const state = driftStateOf(
    {
      live,
      capable,
      analysisId,
      analysis: { candidates: analysis.data?.length ?? null, error: analysis.error },
      drift: { scenario: drift.data, error: drift.error },
      compute: latest,
    },
    {
      compute: () => {
        if (analysisId) compute(analysisId);
      },
      reloadAnalysis: () => void analysis.refetch(),
      reloadDrift: () => void drift.refetch(),
    },
  );
  return { state, candidates };
}

export const useDriftState = (): DriftState => useDriftSource().state;

export function useDriftScenario(): DriftScenario | null {
  const { state } = useDriftSource();
  return state.status === "ready" ? state.scenario : null;
}

export function useDriftCandidates(): Sourced<readonly DriftCandidate[]> {
  const demo = useDemoSourced<readonly DriftCandidate[]>(DEMO_CANDIDATES);
  const { candidates } = useDriftSource();
  if (demo.origin === "demo" || !candidates.length) return demo;
  return { origin: "api", data: candidates };
}

export function useDriftForecasts(): Sourced<readonly DriftForecast[]> {
  const demo = useDemoSourced<readonly DriftForecast[]>(DEMO_FORECASTS);
  const scenario = useDriftScenario();
  return scenario ? { origin: "api", data: scenario.forecasts } : demo;
}

export function useDriftForecastDetails(): Sourced<readonly DriftForecastDetail[]> {
  const demo = useDemoSourced<readonly DriftForecastDetail[]>(DEMO_FORECAST_DETAILS);
  const scenario = useDriftScenario();
  return scenario ? { origin: "api", data: scenario.forecasts } : demo;
}

export function useForecastRun(): Sourced<ForecastRun> {
  const demo = useDemoSourced<ForecastRun>(DEMO_FORECAST_RUN);
  const run = useDriftScenario()?.run;
  return run ? { origin: "api", data: run } : demo;
}

export function useCurrentField(): Sourced<CurrentField> {
  const demo = useDemoSourced<CurrentField>(DEMO_CURRENT_FIELD);
  const field = useDriftScenario()?.field;
  return field ? { origin: "api", data: field } : demo;
}
