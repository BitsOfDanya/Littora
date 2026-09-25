"use client";

import { useCandidates } from "@/data/candidates";
import {
  type DriftForecastDetail,
  type ForecastRun,
  useDriftForecastDetails,
  useForecastRun,
} from "@/data/forecast";
import type { DemoUnavailable } from "@/domain/data-origin";
import type { DebrisCandidate } from "@/domain/detection";
import { useWorkspaceStore } from "@/state/workspace-store";

export type SelectedForecast =
  | { status: "idle" }
  | { status: "planned"; candidateId: string; reason: DemoUnavailable }
  | { status: "missing"; candidateId: string }
  | {
      status: "ready";
      candidate: DebrisCandidate;
      forecast: DriftForecastDetail;
      run: ForecastRun;
      isDemo: boolean;
    };

export function useSelectedForecast(): SelectedForecast {
  const selectedId = useWorkspaceStore((state) => state.selectedCandidateId);
  const candidates = useCandidates();
  const forecasts = useDriftForecastDetails();
  const run = useForecastRun();
  if (!selectedId) return { status: "idle" };
  if (candidates.origin === "none")
    return { status: "planned", candidateId: selectedId, reason: candidates.demo };
  const candidate = candidates.data.find((entry) => entry.id === selectedId);
  if (!candidate) return { status: "idle" };
  if (forecasts.origin === "none")
    return { status: "planned", candidateId: selectedId, reason: forecasts.demo };
  const forecast = forecasts.data.find((entry) => entry.candidateId === selectedId);
  if (!forecast || run.origin === "none") return { status: "missing", candidateId: selectedId };
  return {
    status: "ready",
    candidate,
    forecast,
    run: run.data,
    isDemo: forecasts.origin === "demo",
  };
}
