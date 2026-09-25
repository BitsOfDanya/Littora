"use client";

import { useCandidates } from "@/data/candidates";
import { useForecastCamera } from "./use-forecast-camera";
import { useForecastEmptyHint } from "./use-forecast-hint";
import { useHorizonUrl } from "./use-horizon-url";
import { useSelectedForecast } from "./use-selected-forecast";

export function ForecastEffects() {
  const selected = useSelectedForecast();
  const candidates = useCandidates();
  useHorizonUrl();
  useForecastCamera(selected.status === "ready" ? selected.forecast : null);
  useForecastEmptyHint(selected.status === "idle" && candidates.origin !== "none");
  return null;
}
