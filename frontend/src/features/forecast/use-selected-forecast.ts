"use client";

import type { DriftCandidate, DriftState } from "@/data/drift";
import {
  type DriftForecastDetail,
  type ForecastRun,
  useDriftCandidates,
  useDriftForecastDetails,
  useDriftState,
  useForecastRun,
} from "@/data/forecast";
import type { DemoUnavailable } from "@/domain/data-origin";
import { useWorkspaceStore } from "@/state/workspace-store";

export type SelectedForecast =
  | { status: "idle" }
  | { status: "planned"; candidateId: string; reason: DemoUnavailable }
  | { status: "pending"; candidateId: string; drift: DriftState }
  | { status: "missing"; candidateId: string; drift: DriftState }
  | {
      status: "ready";
      candidate: DriftCandidate;
      forecast: DriftForecastDetail;
      run: ForecastRun;
      isDemo: boolean;
    };

const isLive = (drift: DriftState) => drift.status !== "demo" && drift.status !== "planned";

export function useSelectedForecast(): SelectedForecast {
  const selectedId = useWorkspaceStore((state) => state.selectedCandidateId);
  const candidates = useDriftCandidates();
  const forecasts = useDriftForecastDetails();
  const run = useForecastRun();
  const drift = useDriftState();
  if (!selectedId) return { status: "idle" };
  if (candidates.origin === "none")
    return isLive(drift)
      ? { status: "idle" }
      : { status: "planned", candidateId: selectedId, reason: candidates.demo };
  const candidate = candidates.data.find((entry) => entry.id === selectedId);
  if (!candidate) return { status: "idle" };
  if (forecasts.origin === "none")
    return candidates.origin === "api"
      ? { status: "pending", candidateId: selectedId, drift }
      : { status: "planned", candidateId: selectedId, reason: forecasts.demo };
  const forecast = forecasts.data.find((entry) => entry.candidateId === selectedId);
  if (!forecast || run.origin === "none")
    return { status: "missing", candidateId: selectedId, drift };
  return {
    status: "ready",
    candidate,
    forecast,
    run: run.data,
    isDemo: forecasts.origin === "demo",
  };
}
