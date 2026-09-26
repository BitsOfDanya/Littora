"use client";

import { useDriftCandidates } from "@/data/forecast";
import { useAdoptSavedAnalysis } from "@/features/analysis/use-analysis";
import { useForecastCamera } from "./use-forecast-camera";
import { useFirstZoneSelection } from "./use-first-zone";
import { useForecastEmptyHint } from "./use-forecast-hint";
import { useHorizonUrl } from "./use-horizon-url";
import { useSelectedForecast } from "./use-selected-forecast";

export function ForecastEffects() {
  const selected = useSelectedForecast();
  const candidates = useDriftCandidates();
  useHorizonUrl();
  useAdoptSavedAnalysis();
  useFirstZoneSelection();
  useForecastCamera(
    selected.status === "ready" ? selected.forecast : null,
    selected.status === "ready" && !selected.isDemo,
  );
  useForecastEmptyHint(selected.status === "idle" && candidates.origin !== "none");
  return null;
}
