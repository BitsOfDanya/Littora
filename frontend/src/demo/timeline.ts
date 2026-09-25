import type { CandidateHistory, CandidatePass, PassState } from "@/data/timeline";
import type { DebrisCandidate } from "@/domain/detection";
import type { LngLat } from "@/domain/geo";
import type { Estimate } from "@/domain/measurement";
import type { SceneSummary } from "@/domain/scene";
import { offsetLngLat, polygonAreaM2, toLocalMeters } from "@/lib/geo/local-metric";
import { DEMO_CANDIDATES } from "./candidates";
import { DEMO_SCENES } from "./scenes";

export type CandidateObservation = {
  sceneId: string;
  observedAt: string;
  detected: boolean;
  geometry: GeoJSON.Polygon | null;
  areaM2: number | null;
  coverage: Estimate | null;
};

type HistorySeed = { states: string; driftBearingDeg: number };

const DAY_MS = 86_400_000;
const FALLBACK_AREA_GROWTH_PER_DAY = 0.012;
const FALLBACK_COVERAGE_GROWTH_PER_DAY = 0.01;
const FALLBACK_DRIFT_M_PER_DAY = 60;
const MIN_COVERAGE = 0.02;
const AREA_FACTOR_RANGE: readonly [number, number] = [0.12, 3];

export const DEMO_PASS_CODES: Readonly<Record<string, PassState>> = {
  o: "found",
  "-": "not-found",
  c: "cloudy",
  n: "no-data",
};

export const DEMO_HISTORY_SEEDS: Readonly<Record<string, HistorySeed>> = {
  "001": { states: "-ccn-cnoconooooo", driftBearingDeg: 248 },
  "002": { states: "-c-n--n-conoooco", driftBearingDeg: 256 },
  "003": { states: "--cn--n---n---co", driftBearingDeg: 250 },
  "004": { states: "-c-n-cn---nooooo", driftBearingDeg: 238 },
  "005": { states: "---n-cn-c-n----o", driftBearingDeg: 244 },
  "006": { states: "--cn--n-c-noooco", driftBearingDeg: 265 },
  "007": { states: "---n-cn---n-ocoo", driftBearingDeg: 252 },
};

type Trend = { areaLogRatePerDay: number; coverageSlopePerDay: number; driftMPerDay: number };

function trendOf(candidate: DebrisCandidate): Trend {
  const { change } = candidate;
  if (!change)
    return {
      areaLogRatePerDay: Math.log(1 + FALLBACK_AREA_GROWTH_PER_DAY),
      coverageSlopePerDay: candidate.coverage.value * FALLBACK_COVERAGE_GROWTH_PER_DAY,
      driftMPerDay: FALLBACK_DRIFT_M_PER_DAY,
    };
  const days = (Date.parse(candidate.observedAt) - Date.parse(change.previousObservedAt)) / DAY_MS;
  return {
    areaLogRatePerDay: Math.log(1 + change.areaDeltaRatio) / days,
    coverageSlopePerDay: change.coverageDeltaPoints / 100 / days,
    driftMPerDay: change.displacementM / days,
  };
}

function clamp(value: number, [min, max]: readonly [number, number]): number {
  return Math.min(max, Math.max(min, value));
}

function round(value: number, digits: number): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function coverageAt(candidate: DebrisCandidate, trend: Trend, daysBefore: number): Estimate {
  const { value, low, high } = candidate.coverage;
  const shifted = Math.max(MIN_COVERAGE, value - trend.coverageSlopePerDay * daysBefore);
  return {
    value: round(shifted, 3),
    low: round(shifted * (low / value), 3),
    high: round(shifted * (high / value), 3),
  };
}

function shiftedGeometry(
  candidate: DebrisCandidate,
  scale: number,
  shift: readonly [number, number],
): GeoJSON.Polygon {
  const origin = candidate.centroid;
  const ring = candidate.geometry.coordinates[0].map((position) => {
    const [east, north] = toLocalMeters(origin, [position[0], position[1]]);
    const [lng, lat] = offsetLngLat(origin, [east * scale + shift[0], north * scale + shift[1]]);
    return [lng, lat];
  });
  return { type: "Polygon", coordinates: [ring] };
}

function emptyPass(scene: SceneSummary, state: PassState): CandidatePass {
  return {
    sceneId: scene.id,
    observedAt: scene.acquiredAt,
    state,
    geometry: null,
    centroid: null,
    areaM2: null,
    coverage: null,
  };
}

function foundPass(
  candidate: DebrisCandidate,
  scene: SceneSummary,
  trend: Trend,
  driftBearingDeg: number,
): CandidatePass {
  const daysBefore = (Date.parse(candidate.observedAt) - Date.parse(scene.acquiredAt)) / DAY_MS;
  if (daysBefore <= 0)
    return {
      ...emptyPass(scene, "found"),
      geometry: candidate.geometry,
      centroid: candidate.centroid,
      areaM2: candidate.areaM2,
      coverage: candidate.coverage,
    };
  const areaFactor = clamp(Math.exp(-trend.areaLogRatePerDay * daysBefore), AREA_FACTOR_RANGE);
  const bearing = (driftBearingDeg * Math.PI) / 180;
  const backM = trend.driftMPerDay * daysBefore;
  const shift: [number, number] = [-Math.sin(bearing) * backM, -Math.cos(bearing) * backM];
  const geometry = shiftedGeometry(candidate, Math.sqrt(areaFactor), shift);
  const centroid: LngLat = offsetLngLat(candidate.centroid, shift);
  return {
    ...emptyPass(scene, "found"),
    geometry,
    centroid,
    areaM2: Math.round(polygonAreaM2(geometry)),
    coverage: coverageAt(candidate, trend, daysBefore),
  };
}

function historyOf(candidate: DebrisCandidate): CandidateHistory {
  const seed = DEMO_HISTORY_SEEDS[candidate.id.slice(-3)];
  const trend = trendOf(candidate);
  const passes = DEMO_SCENES.map((scene, index) => {
    if (scene.usability === "unusable") return emptyPass(scene, "no-data");
    const state = DEMO_PASS_CODES[seed?.states[index] ?? "-"] ?? "not-found";
    return state === "found"
      ? foundPass(candidate, scene, trend, seed?.driftBearingDeg ?? 250)
      : emptyPass(scene, state);
  });
  return { candidateId: candidate.id, passes };
}

export const DEMO_CANDIDATE_HISTORIES: readonly CandidateHistory[] = DEMO_CANDIDATES.map(historyOf);

const TRACKED = DEMO_CANDIDATES[0];

export const DEMO_TRACKED_CANDIDATE_ID = TRACKED.id;

export const DEMO_TRACK: readonly CandidateObservation[] = (
  DEMO_CANDIDATE_HISTORIES.find((history) => history.candidateId === TRACKED.id)?.passes ?? []
)
  .filter((pass) => pass.state === "found" || pass.state === "not-found")
  .map((pass) => ({
    sceneId: pass.sceneId,
    observedAt: pass.observedAt,
    detected: pass.state === "found",
    geometry: pass.geometry,
    areaM2: pass.areaM2,
    coverage: pass.coverage,
  }));
