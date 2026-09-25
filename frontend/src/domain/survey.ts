import type { LngLat } from "./geo";
import type { SurveyPriority } from "./detection";

export type SurveyScoreComponent =
  "confidence" | "coverage" | "persistence" | "drift_risk" | "uncertainty" | "accessibility";

export type SurveyTarget = {
  id: string;
  rank: number;
  candidateIds: readonly string[];
  position: LngLat;
  expectedPosition: LngLat | null;
  priority: SurveyPriority;
  score: number;
  components: Readonly<Record<SurveyScoreComponent, number>>;
  uncertainty: number;
  expectedInformationGain: number;
  reason: string;
  distanceFromPortKm: number;
  recommendedMethod: "vessel" | "uav" | "tasking";
};
