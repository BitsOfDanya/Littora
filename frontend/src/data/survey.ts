"use client";

import type { LngLat } from "@/domain/geo";
import type { SentinelPlatform } from "@/domain/scene";
import type { SurveyScoreComponent } from "@/domain/survey";
import { DEMO_SURVEY_PLAN } from "@/demo/survey";
import { useDemoSourced } from "./use-sourced";

export type SurveyMethod = "vessel" | "uav" | "tasking";

export type SurveyPort = { name: string; position: LngLat; berth: LngLat };

export type SurveyDrift = { bearingDeg: number; kmPerDay: number };

export type SurveySearchRadius = { baseKm: number; kmPerDay: number };

export type SurveyScoreWeights = Readonly<Record<SurveyScoreComponent, number>>;

export type SurveyPlanTarget = {
  id: string;
  candidateId: string;
  observedAt: string;
  observedPosition: LngLat;
  components: Readonly<Record<SurveyScoreComponent, number>>;
  reason: string;
  drift: SurveyDrift;
  searchRadius: SurveySearchRadius;
  method: SurveyMethod;
};

export type SurveyRouteStop =
  { kind: "via"; position: LngLat } | { kind: "target"; targetId: string };

export type PlannedPass = {
  id: string;
  platform: SentinelPlatform;
  relativeOrbit: number;
  acquiredAt: string;
  swath: { westLng: number; eastLng: number };
};

export type SurveyPlan = {
  id: string;
  aoiId: string;
  issuedAt: string;
  port: SurveyPort;
  departure: { defaultDate: string; timeUtc: string; utcOffsetH: number };
  window: { from: string; to: string };
  speedKn: number;
  dwellMin: number;
  weights: SurveyScoreWeights;
  route: readonly SurveyRouteStop[];
  targets: readonly SurveyPlanTarget[];
  passes: readonly PlannedPass[];
};

export const SURVEY_DEMO_SOURCE = "demo/survey";

export const useSurveyPlan = () => useDemoSourced<SurveyPlan>(DEMO_SURVEY_PLAN);
