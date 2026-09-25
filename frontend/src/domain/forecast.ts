import type { LngLat } from "./geo";

export const FORECAST_HORIZONS_H = [6, 12, 24, 48, 72] as const;

export type ForecastHorizonH = (typeof FORECAST_HORIZONS_H)[number];

export type CurrentSample = {
  position: LngLat;
  speedMs: number;
  directionDeg: number;
};

export type DriftEnvelope = {
  horizonH: ForecastHorizonH;
  median: LngLat;
  polygon: GeoJSON.Polygon;
  probability: number;
};

export type DriftForecast = {
  candidateId: string;
  issuedAt: string;
  forcing: { currents: string; wind: string; waves: string | null; runAt: string };
  windageRatio: number;
  medianPath: readonly LngLat[];
  envelopes: readonly DriftEnvelope[];
  beachingRisk: { segment: string; probability: number } | null;
};
