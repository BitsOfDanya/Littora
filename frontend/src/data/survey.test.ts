import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { surveySchema } from "@/lib/api/survey";
import {
  countPlannableZones,
  type SurveyInputs,
  type SurveyResult,
  surveyStateOf,
  toSurveyPlan,
  toSurveyResult,
} from "./survey";

const T0 = "2025-09-04T08:37:37.987Z";

const track = Array.from({ length: 73 }, (_, hour) => [37.8 + hour * 0.001, 44.7] as const);

const target = (id: string, rank: number, withDrift: boolean) => ({
  id,
  rank,
  score: 0.8 - rank / 100,
  zone_ids: [`zone-${rank}`, `zone-${rank + 10}`],
  lead_zone: `zone-${rank}`,
  position: [37.8 + rank / 100, 44.7],
  observed_at: T0,
  area_km2: 0.0026,
  pixels: 26,
  probability_max: 0.999,
  probability_mean: 0.71,
  components: {
    confidence: 1,
    coverage: 0.71,
    persistence: null,
    drift_risk: withDrift ? 0.75 : null,
    uncertainty: 0.59,
    accessibility: 0.98,
  },
  reason: "вероятность 1,00 · 2 600 м²",
  why: ["вероятность детектора до 1,00, в среднем 0,71"],
  urgency: {
    level: withDrift ? "high" : "unknown",
    label: withDrift ? "уходит на 1 км за 4 ч, на 2 км — за 6 ч" : "не оценена: дрейф не рассчитан",
    leaves_1km_h: withDrift ? 4 : null,
    leaves_2km_h: withDrift ? 6 : null,
    beaching: withDrift
      ? { name: "Берег у места «Мыс»", severity: "alarm", probability: 0.48, window_h: [4, 20] }
      : null,
    beaching_any: withDrift ? 0.49 : null,
    deadline_h: withDrift ? 4 : null,
  },
  checks: ["подтвердит или снимет детекцию"],
  window: { from: "2025-09-04T11:37:37Z", to: "2025-09-04T12:37:37Z", basis: "светлое время" },
  window_note: null,
  spot_until: withDrift ? "2025-09-04T14:37:37Z" : null,
  nearest_port: { id: "wpi-44200", name: "Новороссийск", distance_km: 1.15 },
  shore_km: withDrift ? 0.74 : null,
  uav: { feasible: true, range_km: 15, basis: "1,1 км от порта — в радиусе 15 км" },
  method: rank === 3 ? "uav" : "vessel",
  drift: withDrift
    ? {
        bearing_deg: 90,
        km_per_day: 1.9,
        hours: 72,
        track,
        radii: [
          { hour: 0, km: 0.18 },
          { hour: 24, km: 0.9 },
        ],
      }
    : null,
  search_radius: { base_km: 0.179, km_per_day: 0.72 },
  visit: rank === 3 ? null : rank,
  eta: rank === 3 ? null : "2025-09-04T11:44:27Z",
  shift_at_eta_km: rank === 3 ? null : 0.95,
});

const response = surveySchema.parse({
  analysis_id: "177f5786e43c6833",
  model: "littora-survey-2",
  status: { status: "estimate", label: "план обследования — расчётный" },
  reason: "расчётный план, а не проверенный маршрут",
  value_kind: "plan",
  request: { speed_kn: 10, uav_range_km: 15, route_targets: 5, dwell_min: 20, lead_h: 3 },
  t0: T0,
  ready_at: "2025-09-04T11:37:37Z",
  drift: {
    used: true,
    status: "scenario",
    computed_at: "2026-09-26T08:23:49+00:00",
    hours: 72,
    note: "срочность и окна — по сценарию дрейфа",
  },
  zones: { total: 35, groups: 24, planned: 3, limit: 12 },
  weights: {
    confidence: 0.3,
    coverage: 0.2,
    persistence: 0,
    drift_risk: 0.2,
    uncertainty: 0.1,
    accessibility: 0.2,
  },
  scoring: { confidence: "максимальная вероятность детектора" },
  port: {
    id: "wpi-44200",
    name: "Новороссийск",
    name_en: "Novorossiysk",
    country: "Russia",
    sea: "Чёрное море",
    harbor_size: "Large",
    harbor_type: "Coastal (Breakwater)",
    position: [37.7833, 44.7167],
    source: "World Port Index, NGA Pub 150",
    distance_km: 2.66,
  },
  targets: [target("SV-01", 1, true), target("SV-02", 2, false), target("SV-03", 3, false)],
  route: {
    port_id: "wpi-44200",
    order: ["SV-02", "SV-01"],
    path: [
      [37.7833, 44.7167],
      [37.82, 44.7],
      [37.81, 44.7],
      [37.7833, 44.7167],
    ],
    legs: [
      { target_id: "SV-02", cumulative_km: 3.1, arrive_h: 0.17 },
      { target_id: "SV-01", cumulative_km: 4, arrive_h: 0.55 },
    ],
    one_way_km: 4,
    distance_km: 6.7,
    duration_h: 1.03,
    speed_kn: 10,
    dwell_min: 20,
    method: "ближайший сосед + 2-opt",
  },
  exit_window: {
    from: "2025-09-04T11:40:00Z",
    to: "2025-09-04T12:30:00Z",
    departure: "2025-09-04T11:40:00Z",
    daylight: ["2025-09-04T02:53:27Z", "2025-09-04T16:02:45Z"],
    beaching_at: "2025-09-04T12:37:37Z",
    scenario_end: "2025-09-07T08:37:37Z",
    relaxed: null,
    basis: "выход не раньше t0 + 3 ч",
    past: true,
  },
  passes: [
    {
      id: "S2C-R121-20250906",
      platform: "S2C",
      relative_orbit: 121,
      acquired_at: "2025-09-06T08:27:59Z",
      swath: [37.0226, 39.1242],
      cloud_cover: 0,
      scenes: 2,
    },
    {
      id: "L8-20250907",
      platform: "L8",
      relative_orbit: null,
      acquired_at: "2025-09-07T08:27:59Z",
      swath: [37, 39],
      cloud_cover: null,
      scenes: 1,
    },
  ],
  passes_note: null,
  messages: ["окно выхода в прошлом"],
  computed_at: "2026-09-26T08:40:00Z",
});

const empty = surveySchema.parse({
  ...response,
  status: { status: "no_zones", label: "нет зон для обследования" },
  reason: "в анализе нет зон детекции — обследовать нечего",
  targets: [],
  route: null,
  exit_window: null,
  port: null,
});

describe("toSurveyPlan", () => {
  const plan = toSurveyPlan(response, "novorossiysk");

  it("maps the planner response into the survey plan", () => {
    expect(plan).not.toBeNull();
    if (!plan) return;
    expect(plan.aoiId).toBe("novorossiysk");
    expect(plan.issuedAt).toBe("2025-09-04T11:37:37Z");
    expect(plan.port).toEqual({
      name: "Новороссийск",
      position: [37.7833, 44.7167],
      berth: [37.7833, 44.7167],
    });
    expect(plan.departure).toEqual({ defaultDate: "2025-09-04", timeUtc: "11:40", utcOffsetH: 3 });
    expect(plan.window).toEqual({ from: "2025-09-04", to: "2025-09-04" });
    expect(plan.speedKn).toBe(10);
    expect(plan.dwellMin).toBe(20);
    expect(plan.route).toEqual([
      { kind: "target", targetId: "SV-02" },
      { kind: "target", targetId: "SV-01" },
      { kind: "via", position: [37.7833, 44.7167] },
    ]);
    expect(plan.passes).toEqual([
      {
        id: "S2C-R121-20250906",
        platform: "S2C",
        relativeOrbit: 121,
        acquiredAt: "2025-09-06T08:27:59Z",
        swath: { westLng: 37.0226, eastLng: 39.1242 },
      },
    ]);
  });

  it("keeps unassessed components out and carries the drift track", () => {
    const [first, second, third] = plan?.targets ?? [];
    expect(first.components).toEqual({
      confidence: 1,
      coverage: 0.71,
      drift_risk: 0.75,
      uncertainty: 0.59,
      accessibility: 0.98,
    });
    expect("persistence" in first.components).toBe(false);
    expect(first.track?.path).toHaveLength(73);
    expect(first.track?.radii[1]).toEqual({ hour: 24, km: 0.9 });
    expect(first.drift).toEqual({ bearingDeg: 90, kmPerDay: 1.9 });
    expect(first.details?.urgency.beaching?.windowH).toEqual([4, 20]);
    expect(first.details?.nearestPort).toEqual({ name: "Новороссийск", distanceKm: 1.15 });
    expect(second.track).toBeUndefined();
    expect(second.drift).toEqual({ bearingDeg: 0, kmPerDay: 0 });
    expect(second.details?.urgency.level).toBe("unknown");
    expect(third.method).toBe("uav");
    expect(third.candidateId).toBe("zone-3");
  });

  it("exposes the honest plan status", () => {
    expect(plan?.meta?.label).toBe("план обследования — расчётный");
    expect(plan?.meta?.exitWindow?.past).toBe(true);
    expect(plan?.meta?.exitWindow?.beachingAt).toBe("2025-09-04T12:37:37Z");
    expect(plan?.meta?.exitWindow?.scenarioEnd).toBe("2025-09-07T08:37:37Z");
    expect(plan?.meta?.drift.used).toBe(true);
    expect(plan?.meta?.options).toEqual({ speedKn: 10, uavRangeKm: 15, routeTargets: 5 });
    expect(plan?.meta?.messages).toEqual(["окно выхода в прошлом"]);
  });

  it("falls back to the readiness time without an exit window", () => {
    const planless = toSurveyPlan({ ...response, exit_window: null, route: null }, "x");
    expect(planless?.departure.timeUtc).toBe("11:37");
    expect(planless?.route).toEqual([]);
    expect(planless?.meta?.exitWindow).toBeNull();
  });

  it("returns no plan for an empty result", () => {
    expect(toSurveyPlan(empty, "x")).toBeNull();
    expect(toSurveyResult(empty, "x")).toEqual({
      analysisId: "177f5786e43c6833",
      status: "no_zones",
      label: "нет зон для обследования",
      reason: "в анализе нет зон детекции — обследовать нечего",
      plan: null,
    });
  });
});

describe("surveyStateOf", () => {
  const actions = { build: vi.fn(), reloadAnalysis: vi.fn(), reloadSurvey: vi.fn() };
  const ready: SurveyResult = toSurveyResult(response, "x");
  const base: SurveyInputs = {
    live: true,
    capable: true,
    analysisId: "177f5786e43c6833",
    analysis: { zones: 35, error: null },
    survey: { result: null, error: null },
    build: null,
    driftReady: false,
  };

  it("walks from planned to ready", () => {
    expect(surveyStateOf({ ...base, live: false }, actions).status).toBe("demo");
    expect(surveyStateOf({ ...base, capable: false }, actions).status).toBe("planned");
    expect(surveyStateOf({ ...base, analysisId: null }, actions).status).toBe("no-analysis");
    expect(surveyStateOf({ ...base, analysis: { zones: null, error: null } }, actions).status).toBe(
      "loading",
    );
    expect(surveyStateOf({ ...base, analysis: { zones: 0, error: null } }, actions)).toEqual({
      status: "no-zones",
      reason: null,
    });
    const absent = surveyStateOf({ ...base, driftReady: true }, actions);
    expect(absent).toMatchObject({ status: "absent", driftReady: true });
    expect(
      surveyStateOf({ ...base, survey: { result: undefined, error: null } }, actions).status,
    ).toBe("loading");
    expect(
      surveyStateOf({ ...base, build: { status: "pending", error: null } }, actions).status,
    ).toBe("building");
    const done = surveyStateOf({ ...base, survey: { result: ready, error: null } }, actions);
    expect(done).toMatchObject({ status: "ready", busy: false });
    const rebuilding = surveyStateOf(
      {
        ...base,
        survey: { result: ready, error: null },
        build: { status: "pending", error: null },
      },
      actions,
    );
    expect(rebuilding).toMatchObject({ status: "ready", busy: true });
  });

  it("reports empty, failed and unavailable plans honestly", () => {
    const noZones = toSurveyResult(empty, "x");
    expect(surveyStateOf({ ...base, survey: { result: noZones, error: null } }, actions)).toEqual({
      status: "no-zones",
      reason: "в анализе нет зон детекции — обследовать нечего",
    });
    const blind: SurveyResult = {
      analysisId: "x",
      status: "insufficient_data",
      label: "недостаточно данных",
      reason: "у анализа нет снимка",
      plan: null,
    };
    expect(
      surveyStateOf({ ...base, survey: { result: blind, error: null } }, actions),
    ).toMatchObject({ status: "unavailable", label: "недостаточно данных" });
    const error = new ApiError({ status: 502, code: "bad_gateway", message: "каталог недоступен" });
    const failed = surveyStateOf({ ...base, build: { status: "error", error } }, actions);
    expect(failed.status).toBe("failed");
    if (failed.status === "failed") {
      failed.retry();
      expect(actions.build).toHaveBeenCalled();
    }
    const unreadable = surveyStateOf({ ...base, survey: { result: null, error } }, actions);
    expect(unreadable.status).toBe("failed");
  });

  it("counts only zones with geometry", () => {
    expect(countPlannableZones([{ geometry: {} }, { centroid: [1, 2] }, { geometry: null }])).toBe(
      1,
    );
  });
});
