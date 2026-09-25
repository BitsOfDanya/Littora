import type { SurveyPlan, SurveyPlanTarget, SurveyScoreWeights } from "@/data/survey";
import type { DebrisCandidate } from "@/domain/detection";
import type { SurveyScoreComponent } from "@/domain/survey";
import { DEMO_CANDIDATES } from "./candidates";
import { DEMO_AOI_ID } from "./scenario";

const COVERAGE_SATURATION = 0.2;

const WEIGHTS: SurveyScoreWeights = {
  confidence: 0.25,
  coverage: 0.15,
  persistence: 0.15,
  drift_risk: 0.15,
  uncertainty: 0.15,
  accessibility: 0.15,
};

type PlannerJudgement = Pick<
  Record<SurveyScoreComponent, number>,
  "drift_risk" | "uncertainty" | "accessibility"
>;

type TargetSeed = Omit<
  SurveyPlanTarget,
  "candidateId" | "observedAt" | "observedPosition" | "components" | "reason"
> & {
  candidateSerial: number;
  judgement: PlannerJudgement;
  reason: (candidate: DebrisCandidate) => string;
};

const round2 = (value: number) => Math.round(value * 100) / 100;

function candidateBySerial(serial: number): DebrisCandidate {
  const candidate = DEMO_CANDIDATES[serial - 1];
  if (!candidate) throw new Error(`Нет демо-кандидата № ${serial}`);
  return candidate;
}

function observedComponents(candidate: DebrisCandidate) {
  return {
    confidence: round2(candidate.confidence.score),
    coverage: round2(Math.min(1, candidate.coverage.value / COVERAGE_SATURATION)),
    persistence: round2(candidate.persistence.detectedIn / candidate.persistence.usablePasses),
  };
}

function growthOf(candidate: DebrisCandidate): string {
  const ratio = candidate.change?.areaDeltaRatio ?? 0;
  return `${ratio >= 0 ? "+" : "−"}${Math.round(Math.abs(ratio) * 100)}\u202F%`;
}

function persistenceOf(candidate: DebrisCandidate): string {
  return `${candidate.persistence.detectedIn} из ${candidate.persistence.usablePasses}`;
}

function buildTarget({
  candidateSerial,
  judgement,
  reason,
  ...seed
}: TargetSeed): SurveyPlanTarget {
  const candidate = candidateBySerial(candidateSerial);
  return {
    ...seed,
    reason: reason(candidate),
    candidateId: candidate.id,
    observedAt: candidate.observedAt,
    observedPosition: candidate.centroid,
    components: { ...observedComponents(candidate), ...judgement },
  };
}

const TARGET_SEEDS: readonly TargetSeed[] = [
  {
    id: "SV-01",
    candidateSerial: 1,
    reason: (candidate) =>
      `Крупное вероятное скопление у выноса Мотагуа: площадь ${growthOf(candidate)}, дрейфует к берегу`,
    judgement: { drift_risk: 0.95, uncertainty: 0.5, accessibility: 0.8 },
    drift: { bearingDeg: 248, kmPerDay: 0.33 },
    searchRadius: { baseKm: 0.25, kmPerDay: 0.14 },
    method: "vessel",
  },
  {
    id: "SV-02",
    candidateSerial: 2,
    reason: (candidate) =>
      `Устойчиво: найдено в ${persistenceOf(candidate)} пригодных пролётов; возможна примесь саргассума`,
    judgement: { drift_risk: 0.45, uncertainty: 0.35, accessibility: 0.8 },
    drift: { bearingDeg: 232, kmPerDay: 0.24 },
    searchRadius: { baseKm: 0.2, kmPerDay: 0.12 },
    method: "vessel",
  },
  {
    id: "SV-03",
    candidateSerial: 3,
    reason: () =>
      "Новое пятно, модель не уверена: рядом судовой след и пена — проверка даст больше всего сведений",
    judgement: { drift_risk: 0.55, uncertainty: 0.85, accessibility: 0.85 },
    drift: { bearingDeg: 262, kmPerDay: 0.45 },
    searchRadius: { baseKm: 0.3, kmPerDay: 0.21 },
    method: "uav",
  },
  {
    id: "SV-04",
    candidateSerial: 6,
    reason: () =>
      "В заливе Аматике у порта; мутная вода снижает уверенность — проверить попутно на выходе",
    judgement: { drift_risk: 0.2, uncertainty: 0.4, accessibility: 0.95 },
    drift: { bearingDeg: 205, kmPerDay: 0.12 },
    searchRadius: { baseKm: 0.15, kmPerDay: 0.07 },
    method: "vessel",
  },
  {
    id: "SV-05",
    candidateSerial: 5,
    reason: () =>
      "Сигнал на границе облака и солнечного блика; проверить в конце выхода или по пролёту 28.09",
    judgement: { drift_risk: 0.3, uncertainty: 0.6, accessibility: 0.35 },
    drift: { bearingDeg: 250, kmPerDay: 0.6 },
    searchRadius: { baseKm: 0.4, kmPerDay: 0.3 },
    method: "uav",
  },
];

export const DEMO_SURVEY_PLAN: SurveyPlan = {
  id: "PLAN-260925-01",
  aoiId: DEMO_AOI_ID,
  issuedAt: "2026-09-25T02:10:00Z",
  port: {
    name: "Пуэрто-Барриос",
    position: [-88.6072, 15.7349],
    berth: [-88.61, 15.7348],
  },
  departure: { defaultDate: "2026-09-25", timeUtc: "14:00", utcOffsetH: -6 },
  window: { from: "2026-09-25", to: "2026-09-29" },
  speedKn: 17,
  dwellMin: 20,
  weights: WEIGHTS,
  route: [
    { kind: "via", position: [-88.615, 15.742] },
    { kind: "via", position: [-88.623, 15.77] },
    { kind: "via", position: [-88.63, 15.83] },
    { kind: "target", targetId: "SV-04" },
    { kind: "via", position: [-88.652, 15.935] },
    { kind: "via", position: [-88.648, 15.988] },
    { kind: "via", position: [-88.575, 15.995] },
    { kind: "target", targetId: "SV-03" },
    { kind: "target", targetId: "SV-02" },
    { kind: "target", targetId: "SV-01" },
    { kind: "target", targetId: "SV-05" },
  ],
  targets: TARGET_SEEDS.map(buildTarget),
  passes: [
    {
      id: "S2B-R140-20260926",
      platform: "S2B",
      relativeOrbit: 140,
      acquiredAt: "2026-09-26T16:10:00Z",
      swath: { westLng: -89.9, eastLng: -88.2 },
    },
    {
      id: "S2C-R097-20260928",
      platform: "S2C",
      relativeOrbit: 97,
      acquiredAt: "2026-09-28T16:05:00Z",
      swath: { westLng: -88.72, eastLng: -87.69 },
    },
  ],
};
