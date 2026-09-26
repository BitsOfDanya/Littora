"use client";

import { useMemo } from "react";
import {
  type SurveyPlan,
  type SurveyPlanMeta,
  type SurveyState,
  useSurveySource,
} from "@/data/survey";
import type { LngLat } from "@/domain/geo";
import {
  buildRoute,
  departureIso,
  type DriftState,
  driftAt,
  etaIso,
  type RankedTarget,
  rankTargets,
  type RouteState,
  windowDates,
} from "./plan-model";
import { useSurveyUiStore } from "./survey-ui-store";

export type SurveyView = {
  plan: SurveyPlan;
  isDemo: boolean;
  meta: SurveyPlanMeta | null;
  ranked: readonly RankedTarget[];
  dates: readonly string[];
  departureDate: string;
  departure: string;
  drift: ReadonlyMap<string, DriftState>;
  route: RouteState;
  eta: ReadonlyMap<string, string>;
};

export function computeSurveyView(
  plan: SurveyPlan,
  isDemo: boolean,
  chosenDate: string | null,
): SurveyView {
  const dates = windowDates(plan.window);
  const departureDate =
    chosenDate && dates.includes(chosenDate) ? chosenDate : plan.departure.defaultDate;
  const departure = departureIso(plan, departureDate);
  const ranked = rankTargets(plan.targets, plan.weights);
  const drift = new Map(plan.targets.map((target) => [target.id, driftAt(target, departure)]));
  const positions = new Map<string, LngLat>([...drift].map(([id, state]) => [id, state.position]));
  const route = buildRoute(plan, positions);
  const eta = new Map(
    route.stops.map((stop) => [
      stop.targetId,
      etaIso(departure, stop, plan.speedKn, plan.dwellMin),
    ]),
  );
  return {
    plan,
    isDemo,
    meta: plan.meta ?? null,
    ranked,
    dates,
    departureDate,
    departure,
    drift,
    route,
    eta,
  };
}

export function useSurveyView(): SurveyView | null {
  const sourced = useSurveySource().plan;
  const chosenDate = useSurveyUiStore((state) => state.departureDate);
  const plan = sourced.origin === "none" ? null : sourced.data;
  const isDemo = sourced.origin === "demo";
  return useMemo(
    () => (plan ? computeSurveyView(plan, isDemo, chosenDate) : null),
    [plan, isDemo, chosenDate],
  );
}

export function useSurveyState(): SurveyState {
  return useSurveySource().state;
}
