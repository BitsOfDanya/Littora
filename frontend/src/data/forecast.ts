"use client";

import {
  DEMO_CURRENT_FIELD,
  DEMO_FORECAST_DETAILS,
  DEMO_FORECAST_RUN,
  DEMO_FORECASTS,
} from "@/demo/forecast";
import type { DriftForecast } from "@/domain/forecast";
import type { LngLat } from "@/domain/geo";
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

export const useDriftForecasts = () => useDemoSourced<readonly DriftForecast[]>(DEMO_FORECASTS);

export const useDriftForecastDetails = () =>
  useDemoSourced<readonly DriftForecastDetail[]>(DEMO_FORECAST_DETAILS);

export const useForecastRun = () => useDemoSourced<ForecastRun>(DEMO_FORECAST_RUN);

export const useCurrentField = () => useDemoSourced<CurrentField>(DEMO_CURRENT_FIELD);
