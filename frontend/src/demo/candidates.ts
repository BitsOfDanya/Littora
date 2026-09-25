import type {
  ChangeSincePrevious,
  ConfidenceClass,
  DebrisCandidate,
  LookAlike,
  ReviewStatus,
  SurveyPriority,
} from "@/domain/detection";
import type { LngLat } from "@/domain/geo";
import type { SceneSummary } from "@/domain/scene";
import {
  centroidOf,
  offsetLngLat,
  polygonAreaM2,
  polylineLengthM,
  toLocalMeters,
} from "@/lib/geo/local-metric";
import { curvedCenterline, windrowPolygon } from "./geometry";
import { DEMO_AOI_ID, DEMO_MODEL } from "./scenario";
import { DEMO_LATEST_SCENE, DEMO_SCENES } from "./scenes";
import { mixedPixelSignature } from "./spectra";

type CandidateSeed = {
  serial: number;
  start: LngLat;
  bearingDeg: number;
  lengthM: number;
  bendM: number;
  widthM: number;
  coverage: readonly [value: number, low: number, high: number];
  confidence: readonly [ConfidenceClass, number];
  priority: SurveyPriority;
  status: ReviewStatus;
  change: { areaDeltaRatio: number; coverageDeltaPoints: number; displacementM: number } | null;
  persistence: readonly [detectedIn: number, usablePasses: number];
  lookAlikes: readonly LookAlike[];
  distanceToCoastM: number;
  turbidity: number;
  wakeDistanceM: number | null;
};

const SEEDS: readonly CandidateSeed[] = [
  {
    serial: 1,
    start: [-88.225, 15.788],
    bearingDeg: 298,
    lengthM: 4200,
    bendM: 300,
    widthM: 34,
    coverage: [0.21, 0.13, 0.3],
    confidence: ["likely", 0.82],
    priority: "high",
    status: "needs_survey",
    change: { areaDeltaRatio: 0.38, coverageDeltaPoints: 4.1, displacementM: 2300 },
    persistence: [5, 7],
    lookAlikes: ["sargassum", "foam"],
    distanceToCoastM: 2100,
    turbidity: 2,
    wakeDistanceM: 900,
  },
  {
    serial: 2,
    start: [-88.355, 15.852],
    bearingDeg: 291,
    lengthM: 3000,
    bendM: -210,
    widthM: 26,
    coverage: [0.14, 0.08, 0.22],
    confidence: ["likely", 0.74],
    priority: "high",
    status: "unreviewed",
    change: { areaDeltaRatio: 0.12, coverageDeltaPoints: 1.3, displacementM: 1400 },
    persistence: [4, 7],
    lookAlikes: ["sargassum"],
    distanceToCoastM: 3400,
    turbidity: 1.5,
    wakeDistanceM: null,
  },
  {
    serial: 3,
    start: [-88.462, 15.968],
    bearingDeg: 318,
    lengthM: 2200,
    bendM: 140,
    widthM: 22,
    coverage: [0.09, 0.04, 0.16],
    confidence: ["possible", 0.58],
    priority: "medium",
    status: "unreviewed",
    change: null,
    persistence: [1, 7],
    lookAlikes: ["ship_wake", "foam"],
    distanceToCoastM: 6800,
    turbidity: 0.5,
    wakeDistanceM: 300,
  },
  {
    serial: 4,
    start: [-88.052, 15.873],
    bearingDeg: 276,
    lengthM: 1800,
    bendM: -100,
    widthM: 18,
    coverage: [0.07, 0.03, 0.13],
    confidence: ["possible", 0.51],
    priority: "medium",
    status: "unreviewed",
    change: { areaDeltaRatio: -0.21, coverageDeltaPoints: -1.8, displacementM: 900 },
    persistence: [3, 7],
    lookAlikes: ["turbid_water"],
    distanceToCoastM: 2900,
    turbidity: 3,
    wakeDistanceM: null,
  },
  {
    serial: 5,
    start: [-88.152, 16.028],
    bearingDeg: 304,
    lengthM: 5000,
    bendM: 380,
    widthM: 16,
    coverage: [0.05, 0.02, 0.1],
    confidence: ["low", 0.34],
    priority: "low",
    status: "unreviewed",
    change: null,
    persistence: [1, 7],
    lookAlikes: ["sun_glint", "cloud_edge"],
    distanceToCoastM: 17_500,
    turbidity: 0,
    wakeDistanceM: null,
  },
  {
    serial: 6,
    start: [-88.628, 15.878],
    bearingDeg: 338,
    lengthM: 1300,
    bendM: 60,
    widthM: 20,
    coverage: [0.11, 0.06, 0.18],
    confidence: ["possible", 0.61],
    priority: "medium",
    status: "unreviewed",
    change: { areaDeltaRatio: 0.05, coverageDeltaPoints: 0.4, displacementM: 350 },
    persistence: [3, 7],
    lookAlikes: ["sargassum"],
    distanceToCoastM: 1600,
    turbidity: 2.5,
    wakeDistanceM: null,
  },
  {
    serial: 7,
    start: [-88.556, 16.046],
    bearingDeg: 309,
    lengthM: 2700,
    bendM: -180,
    widthM: 14,
    coverage: [0.06, 0.02, 0.12],
    confidence: ["low", 0.29],
    priority: "low",
    status: "natural",
    change: null,
    persistence: [2, 7],
    lookAlikes: ["sargassum"],
    distanceToCoastM: 9100,
    turbidity: 0.5,
    wakeDistanceM: null,
  },
];

const PIXEL_AREA_M2 = 100;
const PREVIOUS_SCENE = DEMO_SCENES[DEMO_SCENES.length - 3];
const UNCERTAINTY_CORRIDOR_M = 420;
const UNCERTAINTY_THRESHOLD = 0.45;

export const DEMO_RIVER_MOUTH = { name: "р. Мотагуа", position: [-88.217, 15.717] as LngLat };

function candidateId(serial: number): string {
  const stamp = DEMO_LATEST_SCENE.acquiredAt.slice(2, 10).replaceAll("-", "");
  return `LT-${stamp}-${String(serial).padStart(3, "0")}`;
}

export function unitHash(...values: readonly number[]): number {
  let hash = 2166136261;
  for (const value of values) {
    hash ^= Math.round(value * 1000) | 0;
    hash = Math.imul(hash, 16777619);
    hash ^= hash >>> 13;
  }
  return ((hash >>> 0) % 100_000) / 100_000;
}

function toChange(seed: CandidateSeed["change"]): ChangeSincePrevious | null {
  if (!seed) return null;
  return {
    previousSceneId: PREVIOUS_SCENE.id,
    previousObservedAt: PREVIOUS_SCENE.acquiredAt,
    ...seed,
  };
}

export type CandidateShape = {
  id: string;
  serial: number;
  centerline: readonly LngLat[];
  widthM: number;
  turbidity: number;
  wakeDistanceM: number | null;
  areaInterval: readonly [low: number, high: number];
  uncertainty: number;
  uncertaintyZone: GeoJSON.Polygon | null;
};

type BuiltCandidate = { candidate: DebrisCandidate; shape: CandidateShape };

function buildCandidate(seed: CandidateSeed): BuiltCandidate {
  const centerline = curvedCenterline(seed.start, seed.bearingDeg, seed.lengthM, seed.bendM);
  const geometry = windrowPolygon(centerline, seed.widthM);
  const areaM2 = Math.round(polygonAreaM2(geometry));
  const [value, low, high] = seed.coverage;
  const [confidenceClass, score] = seed.confidence;
  const id = candidateId(seed.serial);
  const spread = 0.08 + (1 - score) * 0.12;
  const uncertainty = Math.round((1 - score) * 100) / 100;
  return {
    candidate: {
      id,
      aoiId: DEMO_AOI_ID,
      sceneId: DEMO_LATEST_SCENE.id,
      observedAt: DEMO_LATEST_SCENE.acquiredAt,
      geometry,
      centroid: centroidOf(centerline),
      shape: seed.lengthM / seed.widthM > 12 ? "windrow" : "patch",
      lengthM: Math.round(polylineLengthM(centerline)),
      areaM2,
      pixelCount: Math.max(1, Math.round(areaM2 / PIXEL_AREA_M2)),
      coverage: { value, low, high },
      confidence: { class: confidenceClass, score },
      priority: seed.priority,
      status: seed.status,
      change: toChange(seed.change),
      persistence: { detectedIn: seed.persistence[0], usablePasses: seed.persistence[1] },
      lookAlikes: seed.lookAlikes,
      distanceToCoastM: seed.distanceToCoastM,
      spectrum: mixedPixelSignature(value, seed.turbidity),
      model: DEMO_MODEL,
    },
    shape: {
      id,
      serial: seed.serial,
      centerline,
      widthM: seed.widthM,
      turbidity: seed.turbidity,
      wakeDistanceM: seed.wakeDistanceM,
      areaInterval: [Math.round(areaM2 * (1 - spread)), Math.round(areaM2 * (1 + spread))],
      uncertainty,
      uncertaintyZone:
        uncertainty >= UNCERTAINTY_THRESHOLD
          ? windrowPolygon(centerline, seed.widthM + UNCERTAINTY_CORRIDOR_M)
          : null,
    },
  };
}

const BUILT: readonly BuiltCandidate[] = SEEDS.map(buildCandidate);

export const DEMO_CANDIDATES: readonly DebrisCandidate[] = BUILT.map((entry) => entry.candidate);

export const DEMO_CANDIDATE_SHAPES: Readonly<Record<string, CandidateShape>> = Object.fromEntries(
  BUILT.map((entry) => [entry.candidate.id, entry.shape]),
);

export function findDemoCandidate(id: string): DebrisCandidate | undefined {
  return DEMO_CANDIDATES.find((candidate) => candidate.id === id);
}

export const COVERAGE_CELL_M = 60;
const GRID_ORIGIN: LngLat = [-88.9, 15.3];
const SAMPLE_STEP_M = 8;

export type CoverageCell = {
  key: string;
  polygon: readonly LngLat[];
  center: LngLat;
  coverage: number;
};

function cellPolygon(column: number, row: number): LngLat[] {
  const x0 = column * COVERAGE_CELL_M;
  const y0 = row * COVERAGE_CELL_M;
  const x1 = x0 + COVERAGE_CELL_M;
  const y1 = y0 + COVERAGE_CELL_M;
  return [
    offsetLngLat(GRID_ORIGIN, [x0, y0]),
    offsetLngLat(GRID_ORIGIN, [x1, y0]),
    offsetLngLat(GRID_ORIGIN, [x1, y1]),
    offsetLngLat(GRID_ORIGIN, [x0, y1]),
    offsetLngLat(GRID_ORIGIN, [x0, y0]),
  ];
}

export function coverageCells(
  centerline: readonly LngLat[],
  widthM: number,
  value: number,
  seed: number,
): CoverageCell[] {
  const local = centerline.map((point) => toLocalMeters(GRID_ORIGIN, point));
  const segmentLengths = local
    .slice(1)
    .map((point, index) => Math.hypot(point[0] - local[index][0], point[1] - local[index][1]));
  const total = segmentLengths.reduce((sum, length) => sum + length, 0) || 1;
  const profiles = new Map<string, { column: number; row: number; profile: number }>();
  let travelled = 0;
  segmentLengths.forEach((length, index) => {
    const [x0, y0] = local[index];
    const [x1, y1] = local[index + 1];
    const normal = [-(y1 - y0) / (length || 1), (x1 - x0) / (length || 1)];
    for (let along = 0; along <= length; along += SAMPLE_STEP_M) {
      const t = (travelled + along) / total;
      const shape = Math.sin(Math.PI * t);
      const halfWidth = (widthM / 2) * Math.max(shape, 0.08) + 6;
      const profile = 0.3 + 0.7 * Math.max(shape, 0) ** 0.8;
      const px = x0 + ((x1 - x0) * along) / (length || 1);
      const py = y0 + ((y1 - y0) * along) / (length || 1);
      for (let offset = -halfWidth; offset <= halfWidth; offset += SAMPLE_STEP_M) {
        const column = Math.floor((px + normal[0] * offset) / COVERAGE_CELL_M);
        const row = Math.floor((py + normal[1] * offset) / COVERAGE_CELL_M);
        const key = `${column}:${row}`;
        const current = profiles.get(key);
        if (!current || current.profile < profile) profiles.set(key, { column, row, profile });
      }
    }
    travelled += length;
  });
  const raw = [...profiles.entries()].map(([key, cell]) => ({
    key,
    ...cell,
    weight: cell.profile * (0.72 + 0.56 * unitHash(cell.column, cell.row, seed)),
  }));
  const mean = raw.reduce((sum, cell) => sum + cell.weight, 0) / Math.max(raw.length, 1);
  return raw
    .map((cell) => {
      const polygon = cellPolygon(cell.column, cell.row);
      const center = offsetLngLat(GRID_ORIGIN, [
        (cell.column + 0.5) * COVERAGE_CELL_M,
        (cell.row + 0.5) * COVERAGE_CELL_M,
      ]);
      const coverage = Math.min(0.35, (cell.weight / (mean || 1)) * value);
      return { key: cell.key, polygon, center, coverage: Math.round(coverage * 1000) / 1000 };
    })
    .filter((cell) => cell.coverage >= 0.01);
}

export function centerlineOfWindrow(polygon: GeoJSON.Polygon): LngLat[] {
  const ring = polygon.coordinates[0] ?? [];
  const points = ring.slice(0, -1);
  const half = Math.floor(points.length / 2);
  return Array.from({ length: half }, (_, index) => {
    const left = points[index];
    const right = points[points.length - 1 - index];
    return [(left[0] + right[0]) / 2, (left[1] + right[1]) / 2] as LngLat;
  });
}

export type ConfuserLikelihood = "excluded" | "unlikely" | "possible" | "unchecked";

export type ConfuserRow = {
  key: LookAlike;
  label: string;
  likelihood: ConfuserLikelihood;
  reason: string;
};

export type ConfuserContext = {
  scene: SceneSummary | undefined;
  nearestCloudM: number | null;
  cloudOverSpot: number;
};

const NDVI_VEGETATION = 0.15;
const FOAM_BLUE = 0.12;
const FDI_THRESHOLD = 0.01;

const decimal = (value: number, digits: number) => value.toFixed(digits).replace(".", ",");
const kilometres = (meters: number) => `${decimal(meters / 1000, 1)} км`;

const GLINT_WORD: Record<SceneSummary["sunGlintRisk"], string> = {
  low: "низкий",
  moderate: "умеренный",
  high: "высокий",
};

function sargassumRow(candidate: DebrisCandidate): ConfuserRow {
  const ndvi = candidate.spectrum.indices.ndvi;
  const likelihood: ConfuserLikelihood =
    ndvi < 0 ? "excluded" : ndvi < NDVI_VEGETATION ? "unlikely" : "possible";
  const relation = ndvi < NDVI_VEGETATION ? "ниже" : "выше";
  return {
    key: "sargassum",
    label: "Саргассум",
    likelihood,
    reason: `NDVI ${decimal(ndvi, 2)} ${relation} порога ${decimal(NDVI_VEGETATION, 2)}`,
  };
}

function foamRow(candidate: DebrisCandidate, shape: CandidateShape): ConfuserRow {
  const blue = candidate.spectrum.candidate.find((band) => band.band === "B02")?.reflectance ?? 0;
  if (shape.wakeDistanceM !== null && candidate.lookAlikes.includes("foam"))
    return {
      key: "foam",
      label: "Пена, кильватер",
      likelihood: "possible",
      reason: `рядом судовой след · ${kilometres(shape.wakeDistanceM)}`,
    };
  return {
    key: "foam",
    label: "Пена, кильватер",
    likelihood: blue < FOAM_BLUE ? "unlikely" : "possible",
    reason: `B02 ${decimal(blue, 3)} — пена ярче, от ${decimal(FOAM_BLUE, 2)}`,
  };
}

function cloudRow(context: ConfuserContext): ConfuserRow {
  const over = Math.round(context.cloudOverSpot * 100);
  if (context.nearestCloudM === null)
    return {
      key: "cloud_edge",
      label: "Край облака",
      likelihood: "unchecked",
      reason: "маска облаков для снимка не получена",
    };
  const distance = kilometres(context.nearestCloudM);
  return {
    key: "cloud_edge",
    label: "Край облака",
    likelihood: context.nearestCloudM > 2000 ? "excluded" : "possible",
    reason: `над пятном ${over} % · до ближайшего облака ${distance}`,
  };
}

function glintRow(candidate: DebrisCandidate, context: ConfuserContext): ConfuserRow {
  const scene = context.scene;
  if (!scene)
    return {
      key: "sun_glint",
      label: "Солнечный блик",
      likelihood: "unchecked",
      reason: "геометрия съёмки неизвестна",
    };
  const flagged = candidate.lookAlikes.includes("sun_glint") || scene.sunGlintRisk === "high";
  return {
    key: "sun_glint",
    label: "Солнечный блик",
    likelihood: flagged ? "possible" : scene.sunGlintRisk === "low" ? "excluded" : "unlikely",
    reason: `зенит ${Math.round(scene.sunZenithDeg)}° · риск бликов ${GLINT_WORD[scene.sunGlintRisk]}`,
  };
}

function wakeRow(candidate: DebrisCandidate, shape: CandidateShape): ConfuserRow {
  if (candidate.lookAlikes.includes("ship_wake"))
    return {
      key: "ship_wake",
      label: "Судовой след",
      likelihood: "possible",
      reason: `вытянут прямо, как след · судно в ${kilometres(shape.wakeDistanceM ?? 0)}`,
    };
  return {
    key: "ship_wake",
    label: "Судовой след",
    likelihood: "unchecked",
    reason: "нет данных AIS за время съёмки",
  };
}

function turbidRow(candidate: DebrisCandidate, shape: CandidateShape): ConfuserRow | null {
  if (!candidate.lookAlikes.includes("turbid_water") && shape.turbidity < 2.5) return null;
  const fdi = candidate.spectrum.indices.fdi;
  return {
    key: "turbid_water",
    label: "Мутная вода",
    likelihood: fdi < FDI_THRESHOLD ? "possible" : "unlikely",
    reason: `FDI ${decimal(fdi, 3)} при пороге ${decimal(FDI_THRESHOLD, 3)} · вынос взвеси рекой`,
  };
}

export function confusersFor(
  candidate: DebrisCandidate,
  shape: CandidateShape,
  context: ConfuserContext,
): ConfuserRow[] {
  const rows = [
    sargassumRow(candidate),
    foamRow(candidate, shape),
    turbidRow(candidate, shape),
    cloudRow(context),
    glintRow(candidate, context),
    wakeRow(candidate, shape),
  ].filter((row): row is ConfuserRow => row !== null);
  const rank: Record<ConfuserLikelihood, number> = {
    possible: 0,
    unlikely: 1,
    unchecked: 2,
    excluded: 3,
  };
  return rows.sort((a, b) => rank[a.likelihood] - rank[b.likelihood]);
}

export type JournalFixtureRow = { at: string; actor: string; text: string };

function shiftedIso(iso: string, minutes: number): string {
  return new Date(Date.parse(iso) + minutes * 60_000).toISOString();
}

export function journalFor(candidate: DebrisCandidate): JournalFixtureRow[] {
  const acquired = candidate.observedAt;
  const fdi = decimal(candidate.spectrum.indices.fdi, 3);
  return [
    {
      at: shiftedIso(acquired, 214),
      actor: "система",
      text: `Сцена ${candidate.sceneId.slice(0, 3)} L2A получена из каталога`,
    },
    {
      at: shiftedIso(acquired, 231),
      actor: "модель",
      text: `Пятно-кандидат выделено · FDI ${fdi} · ${candidate.model.name} ${candidate.model.version}`,
    },
    {
      at: shiftedIso(acquired, 232),
      actor: "модель",
      text: `Доля покрытия ${Math.round(candidate.coverage.value * 100)} % · 90 % ДИ ${Math.round(candidate.coverage.low * 100)}–${Math.round(candidate.coverage.high * 100)}`,
    },
  ];
}
