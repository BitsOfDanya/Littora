"use client";

import { useQuery } from "@tanstack/react-query";
import type { Sourced } from "@/domain/data-origin";
import type { ClassificationMetrics, ModelCard } from "@/domain/model";
import { DEMO_MODEL_REPORT } from "@/demo/models";
import { describeApiError } from "@/lib/api/errors";
import { getModels } from "@/lib/api/models";
import { getMeta } from "@/lib/api/system";
import { queryKeys } from "@/lib/query/query-keys";
import { toModelReport } from "./model-report";
import { useDemoSourced } from "./use-sourced";

export type MetricKey = keyof ClassificationMetrics;

export type Interval = readonly [low: number, high: number];

export type MetricIntervals = Readonly<Record<MetricKey, Interval>>;

export type ClassErrors = { label: string; pixels: number; falsePositives: number };

export type ModelEvaluation = ModelCard & {
  code: string;
  inUse: boolean;
  metricsCi95: MetricIntervals | null;
  valF1?: number | null;
  prAuc?: number | null;
  falsePositivesByClass?: readonly ClassErrors[];
};

export type EvaluationSet = {
  dataset: string;
  split: string;
  patches: number | null;
  positivePixels: number;
  scenes?: number | null;
};

export type ServiceProfile = {
  code: string;
  threshold: number;
  thresholdSource: string | null;
  minPixels: number;
  bands: readonly string[];
  seaMask: string | null;
  validation: string | null;
  tta: boolean | null;
  prAuc: number | null;
  postprocessed: ClassificationMetrics | null;
  serviceMetrics: ClassificationMetrics | null;
  serviceMode: string | null;
  calibration: string | null;
  unlabeledAlarmsPer100Km2: number | null;
};

export type TransferResult = {
  code: string;
  data: string;
  metrics: ClassificationMetrics;
  metricsCi95: MetricIntervals | null;
};

export type DomainShiftCheck = {
  source: string;
  sourceName: string;
  threshold: number;
  results: readonly TransferResult[];
};

export type RegionResult = { region: string; positives: number; metrics: ClassificationMetrics };

export type RegionCheck = {
  run: string;
  name: string;
  protocol: string | null;
  regions: readonly RegionResult[];
  pooled: ClassificationMetrics;
};

export type NegativeClassResult = {
  label: string;
  polygons: number;
  pixels: number;
  alarmPixels: number;
};

export type NegativesCheck = {
  run: string;
  definition: string | null;
  pixels: number;
  alarmPixels: number;
  polygons: number;
  scenes: number;
  windowZones: number;
  classes: readonly NegativeClassResult[];
};

export type DetectionRate = {
  group: string;
  targets: number;
  detected: number;
  rate: number;
  ci95: Interval | null;
  zoneDetected: number | null;
};

export type PlpCheck = {
  description: string | null;
  threshold: string | null;
  targets: number;
  plastic: DetectionRate | null;
  natural: DetectionRate | null;
  bySize: readonly DetectionRate[];
  background: { windows: number; waterKm2: number; zones: number; ringAlarmPixels: number } | null;
};

export type ErrorDifference = { mean: number; confidence: number; ci: Interval };

export type ConcentrationEstimate = {
  report: string;
  baselineMae: number;
  nestedMae: number;
  baselineRmse: number;
  nestedRmse: number;
  difference: ErrorDifference | null;
  gain: boolean;
};

export type ServedConcentration = {
  model: string;
  gain: boolean;
  value: number | null;
  unit: string;
  coverageNominal: number | null;
  coverageEmpirical: number | null;
  reason: string | null;
};

export type ConcentrationProfile = {
  profile: string;
  label: string;
  events: number | null;
  surveyDays: number | null;
  primary: ConcentrationEstimate | null;
  shortlist: ConcentrationEstimate | null;
  served: ServedConcentration | null;
};

export type SatellitePairRow = {
  eventId: string;
  sceneId: string;
  concentration: number | null;
  waterPixels: number | null;
  detectedShare: number | null;
  probabilityP99: number | null;
  fdiP99: number | null;
};

export type SatelliteLinkCheck = {
  events: number;
  correlations: number;
  minPValue: number | null;
  pairs: readonly SatellitePairRow[];
};

export type DriftMethodSummary = {
  model: string;
  label: string;
  reason: string;
  velocity: string;
  integration: string;
  windages: readonly number[];
  stokes: readonly boolean[];
  particles: number;
  members: number;
  diffusivityM2s: number;
  horizonsH: readonly number[];
  maxHindcastHours: number;
  forcing: readonly string[];
  envelopeSpread: string | null;
  errors: readonly DriftErrorRow[];
  coverage: readonly DriftCoverageRow[];
  nominalCoverage: number | null;
};

export type DriftErrorRow = {
  label: string;
  horizonH: number;
  windows: number;
  serviceKm: number;
  stationaryKm: number;
  persistenceKm: number;
};

export type DriftCoverageRow = {
  label: string;
  horizonH: number;
  before: number;
  after: number;
};

export type FlagShareRow = {
  part: string;
  group: string;
  objects: number;
  flagged: number;
  share: number | null;
};

export type FlagDiscriminationRow = {
  part: string;
  measure: string;
  value: number | null;
  ci95: Interval | null;
};

export type ZoneFlagCheck = {
  kind: string;
  title: string;
  rule: string;
  inService: boolean;
  shares: readonly FlagShareRow[];
  discrimination: readonly FlagDiscriminationRow[];
};

export type CollectionRow = {
  run: string;
  inService: boolean;
  part: string;
  mode: string;
  patches: number;
  scenes: number;
  c1F1: number;
  c1Ci95: Interval | null;
  l2aF1: number;
  l2aCi95: Interval | null;
  difference: number;
  differenceCi95: Interval | null;
};

export type CollectionCheck = {
  alignment: string;
  rule: string;
  chosen: string;
  rows: readonly CollectionRow[];
};

export type ServiceRegionRow = {
  region: string;
  scenes: number;
  patches: number;
  debrisPixels: number;
  metrics: ClassificationMetrics;
};

export type ServiceRegionCheck = {
  run: string;
  part: string;
  description: string | null;
  regions: readonly ServiceRegionRow[];
  pooled: ServiceRegionRow;
};

export type ModelEvidence = {
  service: ServiceProfile | null;
  otherTestRuns: number;
  domainShift: readonly DomainShiftCheck[];
  regions: readonly RegionCheck[];
  negatives: NegativesCheck | null;
  plp: PlpCheck | null;
  zoneFlags: readonly ZoneFlagCheck[];
  collection: CollectionCheck | null;
  serviceByRegion: ServiceRegionCheck | null;
  concentration: readonly ConcentrationProfile[];
  satelliteLink: SatelliteLinkCheck | null;
  drift: DriftMethodSummary | null;
  sources: readonly string[];
};

export type ModelReport = {
  evaluationSet: EvaluationSet;
  targetClass: string;
  classes: readonly string[];
  models: readonly ModelEvaluation[];
  source: string;
  evidence?: ModelEvidence;
};

export type ModelReportFetch =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string; retry: () => void };

const CAPABILITY = "model_evaluation";
const META_STALE_MS = 5 * 60_000;
const MODELS_STALE_MS = 10 * 60_000;
const IDLE: ModelReportFetch = { status: "idle" };

function useEvaluationCapable(): boolean {
  const meta = useQuery({
    queryKey: queryKeys.system.meta,
    queryFn: ({ signal }) => getMeta(signal),
    staleTime: META_STALE_MS,
  });
  return (
    meta.data?.capabilities.some(
      (capability) => capability.key === CAPABILITY && capability.status === "available",
    ) ?? false
  );
}

export function useModelReportSource(): { report: Sourced<ModelReport>; fetch: ModelReportFetch } {
  const demo = useDemoSourced(DEMO_MODEL_REPORT, { aoiScoped: false });
  const capable = useEvaluationCapable();
  const live = demo.origin !== "demo" && capable;
  const result = useQuery({
    queryKey: queryKeys.models,
    queryFn: ({ signal }) => getModels(signal),
    enabled: live,
    staleTime: MODELS_STALE_MS,
    select: toModelReport,
  });
  if (demo.origin === "demo") return { report: demo, fetch: IDLE };
  if (live && result.data) return { report: { origin: "api", data: result.data }, fetch: IDLE };
  const none: Sourced<ModelReport> = {
    origin: "none",
    demo: demo.origin === "none" ? demo.demo : "not-provided",
  };
  if (!live) return { report: none, fetch: IDLE };
  if (result.isError)
    return {
      report: none,
      fetch: {
        status: "error",
        message: describeApiError(result.error),
        retry: () => void result.refetch(),
      },
    };
  return { report: none, fetch: { status: "loading" } };
}

export function useModelReport(): Sourced<ModelReport> {
  return useModelReportSource().report;
}
