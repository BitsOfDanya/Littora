"use client";

import { useMemo } from "react";
import { type SurveyPlan, useSurveyPlan } from "@/data/survey";
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
  return { plan, isDemo, ranked, dates, departureDate, departure, drift, route, eta };
}

export function useSurveyView(): SurveyView | null {
  const sourced = useSurveyPlan();
  const chosenDate = useSurveyUiStore((state) => state.departureDate);
  return useMemo(
    () =>
      sourced.origin === "none"
        ? null
        : computeSurveyView(sourced.data, sourced.origin === "demo", chosenDate),
    [sourced, chosenDate],
  );
}
