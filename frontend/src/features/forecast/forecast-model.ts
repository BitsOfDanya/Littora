import type { DriftForecastDetail, ProbabilityEstimate } from "@/data/forecast";
import type { ForecastHorizonH } from "@/domain/forecast";
import type { LngLat } from "@/domain/geo";
import {
  type Displacement,
  displacementOf,
  type EllipseSummary,
  ellipseOf,
  type Reliability,
  reliabilityOf,
} from "./drift-math";

export const RAIL_T0_ID = "forecast-rail-t0";

export type HorizonRow = {
  horizonH: ForecastHorizonH;
  median: LngLat;
  displacement: Displacement;
  ellipse: EllipseSummary;
  beachedShare: number;
  reliability: Reliability;
};

export function horizonRows(forecast: DriftForecastDetail): HorizonRow[] {
  return forecast.envelopes.map((envelope) => ({
    horizonH: envelope.horizonH,
    median: envelope.median,
    displacement: displacementOf(forecast.origin, envelope.median),
    ellipse: ellipseOf(envelope.polygon),
    beachedShare: forecast.beachedByHour[envelope.horizonH] ?? 0,
    reliability: reliabilityOf(envelope.horizonH),
  }));
}

export function horizonRow(
  forecast: DriftForecastDetail,
  horizonH: ForecastHorizonH,
): HorizonRow | undefined {
  return horizonRows(forecast).find((row) => row.horizonH === horizonH);
}

export function topSource(forecast: DriftForecastDetail) {
  const [first] = forecast.sources;
  return first && first.position ? first : null;
}

export function isRanged(estimate: ProbabilityEstimate): boolean {
  return estimate.high - estimate.low >= 0.01;
}
