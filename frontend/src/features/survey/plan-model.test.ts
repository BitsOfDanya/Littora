import { describe, expect, it } from "vitest";
import type { SurveyPlan, SurveyPlanTarget, SurveyScoreWeights } from "@/data/survey";
import {
  alongTrack,
  buildRoute,
  distanceKm,
  driftAt,
  radiusAt,
  rankTargets,
  resolveTargetId,
  scoreOf,
  selectedTargetOf,
  toGpx,
} from "./plan-model";
import { computeSurveyView } from "./use-survey-view";

const WEIGHTS: SurveyScoreWeights = {
  confidence: 0.25,
  coverage: 0.15,
  persistence: 0,
  drift_risk: 0.15,
  uncertainty: 0.15,
  accessibility: 0.15,
};

const tracked: SurveyPlanTarget = {
  id: "SV-01",
  candidateId: "zone-1",
  observedAt: "2025-09-04T08:00:00Z",
  observedPosition: [37.8, 44.7],
  components: { confidence: 1, coverage: 0.5 },
  reason: "тест",
  drift: { bearingDeg: 90, kmPerDay: 1 },
  searchRadius: { baseKm: 0.2, kmPerDay: 0.5 },
  method: "vessel",
  track: {
    path: [
      [37.8, 44.7],
      [37.81, 44.7],
      [37.82, 44.7],
    ],
    radii: [
      { hour: 0, km: 0.2 },
      { hour: 2, km: 1 },
    ],
  },
};

describe("tracked drift", () => {
  it("interpolates the median track and clamps at its end", () => {
    expect(alongTrack(tracked.track?.path ?? [], 0.5)).toEqual([37.805, 44.7]);
    expect(alongTrack(tracked.track?.path ?? [], 10)).toEqual([37.82, 44.7]);
    expect(radiusAt(tracked.track?.radii ?? [], 1, 0)).toBeCloseTo(0.6);
    expect(radiusAt([], 1, 0.3)).toBe(0.3);
    const state = driftAt(tracked, "2025-09-04T09:00:00Z");
    expect(state.position[0]).toBeCloseTo(37.81);
    expect(state.shiftKm).toBeCloseTo(distanceKm([37.8, 44.7], [37.81, 44.7]));
    expect(state.radiusKm).toBeCloseTo(0.6);
    expect(state.days).toBeCloseTo(1 / 24);
  });

  it("scores partial components without the missing ones", () => {
    expect(scoreOf(tracked.components, WEIGHTS)).toBe(0.33);
    expect(rankTargets([tracked], WEIGHTS)[0]).toMatchObject({ rank: 1, score: 0.33 });
  });
});

describe("api plan view", () => {
  const plan: SurveyPlan = {
    id: "PLAN-x",
    aoiId: "novorossiysk",
    weights: WEIGHTS,
    issuedAt: "2025-09-04T11:00:00Z",
    port: { name: "Порт", position: [37.78, 44.71], berth: [37.78, 44.71] },
    departure: { defaultDate: "2025-09-04", timeUtc: "11:00", utcOffsetH: 3 },
    window: { from: "2025-09-04", to: "2025-09-04" },
    speedKn: 10,
    dwellMin: 20,
    route: [
      { kind: "target", targetId: "SV-01" },
      { kind: "via", position: [37.78, 44.71] },
    ],
    targets: [tracked],
    passes: [],
  };

  it("routes from the port and back along drifted positions", () => {
    const view = computeSurveyView(plan, false, null);
    expect(view.departure).toBe("2025-09-04T11:00:00Z");
    expect(view.dates).toEqual(["2025-09-04"]);
    const there = view.drift.get("SV-01")?.position ?? [0, 0];
    expect(there[0]).toBeCloseTo(37.82);
    expect(view.route.path).toHaveLength(3);
    expect(view.route.totalKm).toBeCloseTo(2 * distanceKm([37.78, 44.71], there));
    expect(view.route.stops).toEqual([expect.objectContaining({ targetId: "SV-01", visit: 1 })]);
    expect(view.meta).toBeNull();
  });

  it("builds nothing without a port", () => {
    expect(buildRoute({ ...plan, port: null }, new Map())).toEqual({
      path: [],
      stops: [],
      totalKm: 0,
    });
  });
});

describe("resolveTargetId", () => {
  const grouped: SurveyPlanTarget = {
    ...tracked,
    details: {
      zoneIds: ["zone-1", "zone-7"],
      areaKm2: 0.002,
      pixels: 20,
      probabilityMax: 0.9,
      probabilityMean: 0.7,
      why: [],
      checks: [],
      urgency: {
        level: "unknown",
        label: "не оценена",
        leaves1kmH: null,
        leaves2kmH: null,
        beaching: null,
      },
      window: null,
      windowNote: null,
      spotUntil: null,
      nearestPort: null,
      shoreKm: null,
      uav: { feasible: null, rangeKm: 15, basis: "" },
      visit: null,
      eta: null,
      shiftAtEtaKm: null,
    },
  };

  it("maps a selected detector zone to the target that groups it", () => {
    expect(resolveTargetId([grouped], "SV-01")).toBe("SV-01");
    expect(resolveTargetId([grouped], "zone-7")).toBe("SV-01");
    expect(resolveTargetId([grouped], "zone-9")).toBe("zone-9");
    expect(resolveTargetId([grouped], null)).toBeNull();
  });

  it("carries a zone picked in another mode over to its survey target", () => {
    expect(selectedTargetOf([grouped], null, "zone-7")).toBe("SV-01");
    expect(selectedTargetOf([grouped], null, "zone-9")).toBeNull();
    expect(selectedTargetOf([grouped], "SV-01", "zone-9")).toBe("SV-01");
    expect(selectedTargetOf([tracked], null, "zone-1")).toBeNull();
  });
});

describe("toGpx", () => {
  it("writes waypoints once and the full route with escaped names", () => {
    const gpx = toGpx("План <тест> & маршрут", [
      { name: "Порт", position: [37.78, 44.71], note: "выход" },
      { name: "SV-01", position: [37.82, 44.7], note: 'вероятность "1"' },
      { name: "Порт", position: [37.78, 44.71], note: "возврат" },
    ]);
    expect(gpx).toContain("<name>План &lt;тест&gt; &amp; маршрут</name>");
    expect(gpx.match(/<wpt /g)).toHaveLength(2);
    expect(gpx.match(/<rtept /g)).toHaveLength(3);
    expect(gpx).toContain('lat="44.700000" lon="37.820000"');
    expect(gpx).toContain("&quot;1&quot;");
  });
});
