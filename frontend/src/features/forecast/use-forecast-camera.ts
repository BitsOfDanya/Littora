"use client";

import { useMemo } from "react";
import type { DriftForecastDetail } from "@/data/forecast";
import type { LngLat } from "@/domain/geo";
import { useFrameOnce } from "@/features/map/use-frame-once";
import { boundsOf } from "./drift-math";

const FIT_MAX_ZOOM = 11.5;
const CRAMPED_SHARE = 0.15;

function framingPoints(forecast: DriftForecastDetail): LngLat[] {
  return [
    ...forecast.medianPath,
    ...forecast.hindcastPath,
    ...forecast.envelopes.flatMap(
      (envelope) => envelope.polygon.coordinates[0] as unknown as LngLat[],
    ),
    ...forecast.beaching.filter((risk) => risk.severity !== "info").flatMap((risk) => risk.path),
  ];
}

export function useForecastCamera(forecast: DriftForecastDetail | null, tighten = false): void {
  const bbox = useMemo(() => (forecast ? boundsOf(framingPoints(forecast)) : null), [forecast]);
  useFrameOnce(forecast?.candidateId ?? null, bbox, {
    maxZoom: FIT_MAX_ZOOM,
    crampedShare: CRAMPED_SHARE,
    tighten,
    resetOnNull: true,
  });
}
