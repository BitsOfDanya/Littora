import type { ConfidenceClass } from "@/domain/detection";
import { FORECAST_HORIZONS_H, type ForecastHorizonH } from "@/domain/forecast";
import type { AnalysisZone } from "@/lib/api/analyses";
import type {
  DriftCurrentField,
  DriftForecastItem,
  DriftResponse,
  DriftResultStatus,
  DriftRunItem,
} from "@/lib/api/drift";
import { describeApiError } from "@/lib/api/errors";
import type { CurrentField, DriftForecastDetail, ForecastRun } from "./forecast";

export type DriftCandidate = {
  id: string;
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon;
  confidence: { class: ConfidenceClass } | null;
};

export type DriftScenario = {
  analysisId: string;
  status: DriftResultStatus;
  label: string;
  reason: string;
  hours: number;
  zones: { total: number; computed: number; limit: number };
  run: ForecastRun | null;
  waves: string | null;
  windageRatios: readonly number[];
  forecasts: readonly DriftForecastDetail[];
  field: CurrentField | null;
  messages: readonly string[];
};

export type DriftState =
  | { status: "demo" }
  | { status: "planned" }
  | { status: "no-analysis" }
  | { status: "loading" }
  | { status: "no-zones"; reason: string | null }
  | { status: "absent"; compute: () => void }
  | { status: "computing" }
  | { status: "failed"; message: string; retry: () => void }
  | { status: "unavailable"; label: string; reason: string; retry: () => void }
  | { status: "ready"; scenario: DriftScenario };

export type DriftInputs = {
  live: boolean;
  capable: boolean;
  analysisId: string | null;
  analysis: { candidates: number | null; error: unknown };
  drift: { scenario: DriftScenario | null | undefined; error: unknown };
  compute: { status: "idle" | "pending" | "success" | "error"; error: unknown } | null;
};

export type DriftActions = {
  compute: () => void;
  reloadAnalysis: () => void;
  reloadDrift: () => void;
};

type Bracket = { low: number; high: number; t: number };

type Grid<T> = readonly (readonly T[])[];

const isHorizon = (hours: number): hours is ForecastHorizonH =>
  FORECAST_HORIZONS_H.some((horizon) => horizon === hours);

export function toDriftCandidates(zones: readonly AnalysisZone[]): DriftCandidate[] {
  return zones
    .filter((zone) => zone.geometry)
    .flatMap((zone, index) => {
      const geometry = zone.geometry;
      if (geometry?.type !== "Polygon" && geometry?.type !== "MultiPolygon") return [];
      return [{ id: zone.id || `zone-${index + 1}`, geometry, confidence: null }];
    });
}

export function toForecastRun(run: DriftRunItem): ForecastRun {
  return {
    t0: run.t0,
    runAt: run.run_at,
    issuedAt: run.issued_at,
    ensembleSize: run.ensemble_size,
    windageRatio: run.windage_ratio,
    windFromDeg: run.wind_from_deg,
    windSpeedMs: run.wind_speed_ms,
    hindcastHours: run.hindcast_hours,
    currents: run.currents,
    wind: run.wind,
    model: run.model,
  };
}

export function toDriftForecastDetail(item: DriftForecastItem): DriftForecastDetail {
  return {
    candidateId: item.candidate_id,
    issuedAt: item.issued_at,
    forcing: {
      currents: item.forcing.currents,
      wind: item.forcing.wind,
      waves: item.forcing.waves,
      runAt: item.forcing.run_at,
    },
    windageRatio: item.windage_ratio,
    medianPath: item.median_path,
    envelopes: item.envelopes.flatMap((envelope) =>
      isHorizon(envelope.horizon_h)
        ? [
            {
              horizonH: envelope.horizon_h,
              median: envelope.median,
              polygon: envelope.polygon,
              probability: envelope.probability,
            },
          ]
        : [],
    ),
    beachingRisk: item.beaching_risk,
    origin: item.origin,
    hindcastPath: item.hindcast_path,
    beachedByHour: item.beached_by_hour,
    beaching: item.beaching.map((risk) => ({
      id: risk.id,
      name: risk.name,
      severity: risk.severity,
      probability: risk.probability,
      members: risk.members,
      windowH: risk.window_h,
      path: risk.path,
      labelAt: risk.label_at,
    })),
    beachingAny: item.beaching_any,
    sources: item.sources.map((source) => ({
      id: source.id,
      name: source.name,
      position: source.position,
      probability: source.probability,
      members: source.members,
    })),
  };
}

function bracket(axis: readonly number[], value: number): Bracket | null {
  const last = axis.length - 1;
  if (last < 0 || !(value >= axis[0] && value <= axis[last])) return null;
  if (last === 0) return { low: 0, high: 0, t: 0 };
  let low = 0;
  while (low < last - 1 && axis[low + 1] <= value) low += 1;
  const span = axis[low + 1] - axis[low];
  return { low, high: low + 1, t: span > 0 ? (value - axis[low]) / span : 0 };
}

function blend(grid: Grid<number | null>, x: Bracket, y: Bracket): number | null {
  let sum = 0;
  let weight = 0;
  const corners = [
    [y.low, x.low, (1 - y.t) * (1 - x.t)],
    [y.low, x.high, (1 - y.t) * x.t],
    [y.high, x.low, y.t * (1 - x.t)],
    [y.high, x.high, y.t * x.t],
  ] as const;
  for (const [row, column, share] of corners) {
    const value = grid[row]?.[column];
    if (share > 0 && typeof value === "number") {
      sum += value * share;
      weight += share;
    }
  }
  return weight > 0 ? sum / weight : null;
}

function maskLookup(mask: DriftCurrentField["mask"]) {
  const [west, south, east, north] = mask.bounds;
  const cellLng = (east - west) / mask.cols;
  const cellLat = (north - south) / mask.rows;
  return (lng: number, lat: number): boolean | null => {
    const column = Math.floor((lng - west) / cellLng);
    const row = Math.floor((north - lat) / cellLat);
    if (!(column >= 0 && column < mask.cols && row >= 0 && row < mask.rows)) return null;
    const cell = mask.data[row]?.[column];
    return cell === undefined ? null : cell === mask.water;
  };
}

function nodeWater(water: Grid<boolean>, x: Bracket, y: Bracket): boolean {
  return water[y.t < 0.5 ? y.low : y.high]?.[x.t < 0.5 ? x.low : x.high] ?? false;
}

export function toCurrentField(field: DriftCurrentField): CurrentField {
  const masked = maskLookup(field.mask);
  const isWater = (lng: number, lat: number): boolean => {
    const cell = masked(lng, lat);
    if (cell !== null) return cell;
    const x = bracket(field.lons, lng);
    const y = bracket(field.lats, lat);
    return x !== null && y !== null && nodeWater(field.water, x, y);
  };
  return {
    label: field.label,
    bounds: field.bounds,
    typicalSpeedMs: field.typical_speed_ms,
    velocityAt: (lng, lat) => {
      const x = bracket(field.lons, lng);
      const y = bracket(field.lats, lat);
      if (!x || !y || !isWater(lng, lat)) return null;
      const east = blend(field.u, x, y);
      const north = blend(field.v, x, y);
      return east === null || north === null ? null : [east, north];
    },
    isWater,
  };
}

export function toDriftScenario(response: DriftResponse): DriftScenario {
  const { run } = response;
  return {
    analysisId: response.analysis_id,
    status: response.status.status,
    label: response.status.label,
    reason: response.reason,
    hours: response.request.hours,
    zones: response.zones,
    run: run ? toForecastRun(run) : null,
    waves: run?.waves ?? null,
    windageRatios: run?.windage_ratios ?? [],
    forecasts: response.forecasts.map(toDriftForecastDetail),
    field: response.current_field ? toCurrentField(response.current_field) : null,
    messages: response.messages,
  };
}

export function driftStateOf(input: DriftInputs, actions: DriftActions): DriftState {
  if (!input.live) return { status: "demo" };
  if (!input.capable) return { status: "planned" };
  if (!input.analysisId) return { status: "no-analysis" };
  if (input.analysis.error)
    return {
      status: "failed",
      message: `Анализ не загружен: ${describeApiError(input.analysis.error)}`,
      retry: actions.reloadAnalysis,
    };
  if (input.analysis.candidates === null) return { status: "loading" };
  if (input.analysis.candidates === 0) return { status: "no-zones", reason: null };
  if (input.compute?.status === "pending") return { status: "computing" };
  const { scenario } = input.drift;
  if (scenario?.status === "scenario") return { status: "ready", scenario };
  if (scenario?.status === "no_zones") return { status: "no-zones", reason: scenario.reason };
  if (input.compute?.status === "error")
    return {
      status: "failed",
      message: describeApiError(input.compute.error),
      retry: actions.compute,
    };
  if (scenario?.status === "insufficient_data")
    return {
      status: "unavailable",
      label: scenario.label,
      reason: scenario.reason,
      retry: actions.compute,
    };
  if (input.drift.error)
    return {
      status: "failed",
      message: describeApiError(input.drift.error),
      retry: actions.reloadDrift,
    };
  if (scenario === undefined) return { status: "loading" };
  return { status: "absent", compute: actions.compute };
}
