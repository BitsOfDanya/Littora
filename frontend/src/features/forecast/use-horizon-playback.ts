"use client";

import { useEffect } from "react";
import { FORECAST_HORIZONS_H } from "@/domain/forecast";
import { useWorkspaceStore } from "@/state/workspace-store";
import { stepHorizon } from "./drift-math";
import { useForecastUiStore } from "./forecast-ui-store";

export const PLAYBACK_STEP_MS = 1_200;

const LAST_HORIZON = FORECAST_HORIZONS_H[FORECAST_HORIZONS_H.length - 1];

export function startPlayback(): void {
  const { forecastHorizonH, setForecastHorizon } = useWorkspaceStore.getState();
  if (forecastHorizonH === LAST_HORIZON) setForecastHorizon(FORECAST_HORIZONS_H[0]);
  useForecastUiStore.getState().setPlaying(true);
}

export function togglePlayback(): void {
  if (useForecastUiStore.getState().playing) useForecastUiStore.getState().setPlaying(false);
  else startPlayback();
}

export function useHorizonPlayback(enabled: boolean): void {
  const playing = useForecastUiStore((state) => state.playing);
  const setPlaying = useForecastUiStore((state) => state.setPlaying);

  useEffect(() => {
    if (!enabled && playing) setPlaying(false);
  }, [enabled, playing, setPlaying]);

  useEffect(() => () => useForecastUiStore.getState().setPlaying(false), []);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      const { forecastHorizonH, setForecastHorizon } = useWorkspaceStore.getState();
      const next = stepHorizon(forecastHorizonH, 1);
      if (next !== forecastHorizonH) setForecastHorizon(next);
      if (next === LAST_HORIZON) useForecastUiStore.getState().setPlaying(false);
    }, PLAYBACK_STEP_MS);
    return () => window.clearInterval(timer);
  }, [playing]);
}
