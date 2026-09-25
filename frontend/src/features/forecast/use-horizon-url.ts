"use client";

import { useEffect, useRef } from "react";
import { FORECAST_HORIZONS_H, type ForecastHorizonH } from "@/domain/forecast";
import { useWorkspaceStore } from "@/state/workspace-store";

const PARAM = "h";
const WRITE_DEBOUNCE_MS = 400;

function parseHorizon(value: string | null): ForecastHorizonH | undefined {
  const hours = Number(value);
  return FORECAST_HORIZONS_H.find((horizon) => horizon === hours);
}

export function useHorizonUrl(): void {
  const horizonH = useWorkspaceStore((state) => state.forecastHorizonH);
  const setHorizon = useWorkspaceStore((state) => state.setForecastHorizon);
  const readRef = useRef(false);

  useEffect(() => {
    if (readRef.current) return;
    readRef.current = true;
    const fromUrl = parseHorizon(new URLSearchParams(window.location.search).get(PARAM));
    if (fromUrl !== undefined && fromUrl !== useWorkspaceStore.getState().forecastHorizonH)
      setHorizon(fromUrl);
  }, [setHorizon]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams(window.location.search);
      if (params.get(PARAM) === String(horizonH)) return;
      params.set(PARAM, String(horizonH));
      window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
    }, WRITE_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [horizonH]);
}
