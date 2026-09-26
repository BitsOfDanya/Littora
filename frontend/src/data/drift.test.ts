import { describe, expect, it, vi } from "vitest";
import type { AnalysisZone } from "@/lib/api/analyses";
import { driftSchema } from "@/lib/api/drift";
import { ApiError } from "@/lib/api/errors";
import {
  type DriftInputs,
  type DriftScenario,
  driftStateOf,
  toDriftCandidates,
  toDriftScenario,
} from "./drift";

const square = (west: number, south: number, size: number) => ({
  type: "Polygon" as const,
  coordinates: [
    [
      [west, south],
      [west + size, south],
      [west + size, south + size],
      [west, south + size],
      [west, south],
    ] as [number, number][],
  ],
});

const envelope = (horizon: number, afloat: number) => ({
  horizon_h: horizon,
  median: [29.66819, 43.57318],
  polygon: square(29.66, 43.56, 0.02),
  probability: Math.round(0.9 * afloat * 1000) / 1000,
  afloat,
});

const response = {
  analysis_id: "e2e0000000000001",
  model: "littora-drift-1",
  status: { status: "scenario", label: "сценарий дрейфа" },
  reason: "сценарий, а не проверенный прогноз: с дрифтерами не сверялся, точность не оценена",
  value_kind: "scenario",
  request: { hours: 72, hindcast_hours: 48 },
  computed_at: "2026-09-26T00:24:54+00:00",
  zones: { total: 2, computed: 1, limit: 1 },
  run: {
    t0: "2024-06-02T08:58:20.214000Z",
    run_at: "2026-09-26T00:22:17+00:00",
    issued_at: "2026-09-26T00:24:54+00:00",
    ensemble_size: 320,
    windage_ratio: 0.015,
    windage_ratios: [0.005, 0.01, 0.02, 0.03],
    wind_from_deg: 136,
    wind_speed_ms: 3.7,
    wind_window_h: [0, 72],
    hours: 72,
    hindcast_hours: 48,
    currents: "Open-Meteo Marine · MeteoFrance SMOC 1/12°",
    wind: "Open-Meteo Archive · ERA5 0,25°",
    waves: "Open-Meteo Marine · MeteoFrance MFWAM 1/12° → стоксов дрейф",
    model: "littora-drift-1",
  },
  forcing: { currents: { available: true, filled_hours: 11, quantum_ms: 0.05 } },
  method: { members_per_zone: 320 },
  current_field: {
    label: "Течение SMOC на t0 (с волновым дрейфом, без парусности)",
    time: "2024-06-02T09:00:00Z",
    units: "м/с",
    bounds: [30.0, 44.0, 30.2, 44.1],
    lons: [30.0, 30.1, 30.2],
    lats: [44.0, 44.1],
    u: [
      [0.1, 0.2, null],
      [0.3, 0.4, null],
    ],
    v: [
      [0, 0, null],
      [0.1, 0.1, null],
    ],
    water: [
      [true, true, false],
      [true, true, false],
    ],
    typical_speed_ms: 0.11,
    mask: {
      bounds: [30.0, 44.0, 30.1, 44.1],
      rows: 2,
      cols: 2,
      row_order: "north_to_south",
      water: "1",
      data: ["10", "11"],
    },
  },
  forecasts: [
    {
      candidate_id: "zone-1",
      issued_at: "2026-09-26T00:24:54+00:00",
      forcing: {
        currents: "Open-Meteo Marine · MeteoFrance SMOC 1/12°",
        wind: "Open-Meteo Archive · ERA5 0,25°",
        waves: null,
        run_at: "2026-09-26T00:22:17+00:00",
      },
      windage_ratio: 0.015,
      origin: [29.7, 43.6],
      median_path: [
        [29.69986, 43.60005],
        [29.70253, 43.60506],
      ],
      envelopes: [envelope(6, 1), envelope(9, 1), envelope(72, 0.5)],
      beaching_risk: { segment: "Берег у места «Анапа»", probability: 0.5 },
      hindcast_path: [
        [29.81043, 43.43433],
        [29.69986, 43.60005],
      ],
      beached_by_hour: [0, 0.5],
      beaching: [
        {
          id: "coast-1",
          name: "Берег у места «Анапа»",
          severity: "alarm",
          probability: { value: 0.5, low: 0.454, high: 0.546 },
          members: 160,
          window_h: [6, 9],
          path: [
            [37.2, 45.0],
            [37.21, 45.01],
          ],
          label_at: [37.21, 45.01],
        },
      ],
      beaching_any: { value: 0.5, low: 0.454, high: 0.546 },
      sources: [
        {
          id: "port-anapa",
          name: "Порт Анапа",
          kind: "port",
          position: [37.3, 44.9],
          probability: { value: 0.2, low: 0.166, high: 0.239 },
          members: 64,
          hours_back: 30,
        },
      ],
      variants: [],
      members: 320,
      left_domain: 0,
    },
  ],
  messages: ["компоненты течения в ответе Open-Meteo квантованы с шагом 0,05 м/с"],
};

function scenarioOf(payload: unknown = response): DriftScenario {
  return toDriftScenario(driftSchema.parse(payload));
}

describe("drift response mapping", () => {
  it("maps the run onto the forecast run used by the rail and inspector", () => {
    const scenario = scenarioOf();
    expect(scenario.status).toBe("scenario");
    expect(scenario.run).toEqual({
      t0: "2024-06-02T08:58:20.214000Z",
      runAt: "2026-09-26T00:22:17+00:00",
      issuedAt: "2026-09-26T00:24:54+00:00",
      ensembleSize: 320,
      windageRatio: 0.015,
      windFromDeg: 136,
      windSpeedMs: 3.7,
      hindcastHours: 48,
      currents: "Open-Meteo Marine · MeteoFrance SMOC 1/12°",
      wind: "Open-Meteo Archive · ERA5 0,25°",
      model: "littora-drift-1",
    });
    expect(scenario.waves).toContain("MFWAM");
    expect(scenario.windageRatios).toEqual([0.005, 0.01, 0.02, 0.03]);
    expect(scenario.zones).toEqual({ total: 2, computed: 1, limit: 1 });
    expect(scenario.messages).toHaveLength(1);
  });

  it("keeps the ensemble share inside each contour and drops unknown horizons", () => {
    const [forecast] = scenarioOf().forecasts;
    expect(forecast.envelopes.map((entry) => entry.horizonH)).toEqual([6, 72]);
    expect(forecast.envelopes.map((entry) => entry.probability)).toEqual([0.9, 0.45]);
    expect(forecast.origin).toEqual([29.7, 43.6]);
    expect(forecast.hindcastPath.at(-1)).toEqual(forecast.medianPath[0]);
    expect(forecast.forcing).toEqual({
      currents: "Open-Meteo Marine · MeteoFrance SMOC 1/12°",
      wind: "Open-Meteo Archive · ERA5 0,25°",
      waves: null,
      runAt: "2026-09-26T00:22:17+00:00",
    });
  });

  it("maps beaching stretches and source estimates without extra fields", () => {
    const [forecast] = scenarioOf().forecasts;
    expect(forecast.beaching[0]).toEqual({
      id: "coast-1",
      name: "Берег у места «Анапа»",
      severity: "alarm",
      probability: { value: 0.5, low: 0.454, high: 0.546 },
      members: 160,
      windowH: [6, 9],
      path: [
        [37.2, 45.0],
        [37.21, 45.01],
      ],
      labelAt: [37.21, 45.01],
    });
    expect(forecast.beachingRisk).toEqual({ segment: "Берег у места «Анапа»", probability: 0.5 });
    expect(forecast.sources).toEqual([
      {
        id: "port-anapa",
        name: "Порт Анапа",
        position: [37.3, 44.9],
        probability: { value: 0.2, low: 0.166, high: 0.239 },
        members: 64,
      },
    ]);
  });

  it("interpolates currents between water nodes and stops on land", () => {
    const field = scenarioOf().field!;
    expect(field.label).toContain("SMOC");
    expect(field.typicalSpeedMs).toBe(0.11);
    const [east, north] = field.velocityAt(30.025, 44.075)!;
    expect(east).toBeCloseTo(0.275, 6);
    expect(north).toBeCloseTo(0.075, 6);
    expect(field.isWater(30.075, 44.075)).toBe(false);
    expect(field.velocityAt(30.075, 44.075)).toBeNull();
    expect(field.isWater(30.025, 44.025)).toBe(true);
  });

  it("falls back to the forcing grid outside the scene mask and ignores land nodes", () => {
    const field = scenarioOf().field!;
    expect(field.isWater(30.12, 44.02)).toBe(true);
    const [east, north] = field.velocityAt(30.12, 44.02)!;
    expect(east).toBeCloseTo(0.24, 6);
    expect(north).toBeCloseTo(0.02, 6);
    expect(field.isWater(30.19, 44.05)).toBe(false);
    expect(field.velocityAt(30.19, 44.05)).toBeNull();
    expect(field.velocityAt(29.9, 44.05)).toBeNull();
    expect(field.isWater(29.9, 44.05)).toBe(false);
  });

  it("reads a scenario without zones as an empty result", () => {
    const scenario = scenarioOf({
      ...response,
      status: { status: "no_zones", label: "нет зон для дрейфа" },
      reason: "в анализе нет зон детекции — дрейф не рассчитывается",
      zones: { total: 0, computed: 0, limit: 25 },
      run: null,
      current_field: null,
      forecasts: [],
      messages: [],
    });
    expect(scenario.run).toBeNull();
    expect(scenario.field).toBeNull();
    expect(scenario.waves).toBeNull();
    expect(scenario.windageRatios).toEqual([]);
  });
});

describe("detector zones as drift candidates", () => {
  it("numbers zones the way the drift service does and keeps only areas", () => {
    const zones: AnalysisZone[] = [
      { id: "zone-1", geometry: square(29.7, 43.6, 0.001) },
      { geometry: null },
      { geometry: { type: "Point", coordinates: [29.8, 43.7] } },
      { geometry: square(29.9, 43.8, 0.001) },
    ];
    const candidates = toDriftCandidates(zones);
    expect(candidates.map((candidate) => candidate.id)).toEqual(["zone-1", "zone-3"]);
    expect(candidates.every((candidate) => candidate.confidence === null)).toBe(true);
  });
});

describe("drift state", () => {
  const scenario = scenarioOf();
  const base: DriftInputs = {
    live: true,
    capable: true,
    analysisId: "e2e0000000000001",
    analysis: { candidates: 2, error: null },
    drift: { scenario: null, error: null },
    compute: null,
  };
  const actions = { compute: vi.fn(), reloadAnalysis: vi.fn(), reloadDrift: vi.fn() };
  const state = (patch: Partial<DriftInputs>) => driftStateOf({ ...base, ...patch }, actions);

  it("leaves demo fixtures and the planned capability untouched", () => {
    expect(state({ live: false }).status).toBe("demo");
    expect(state({ capable: false }).status).toBe("planned");
  });

  it("asks for an analysis with detector zones first", () => {
    expect(state({ analysisId: null }).status).toBe("no-analysis");
    expect(state({ analysis: { candidates: null, error: null } }).status).toBe("loading");
    expect(state({ analysis: { candidates: 0, error: null } })).toEqual({
      status: "no-zones",
      reason: null,
    });
  });

  it("offers to compute a scenario that is not cached yet", () => {
    const absent = state({});
    expect(absent.status).toBe("absent");
    if (absent.status === "absent") absent.compute();
    expect(actions.compute).toHaveBeenCalled();
    expect(state({ drift: { scenario: undefined, error: null } }).status).toBe("loading");
    expect(state({ compute: { status: "pending", error: null } }).status).toBe("computing");
  });

  it("returns the scenario once it is computed", () => {
    const ready = state({ drift: { scenario, error: null } });
    expect(ready).toEqual({ status: "ready", scenario });
  });

  it("reports failures with a retry instead of an empty map", () => {
    const failed = state({
      compute: {
        status: "error",
        error: new ApiError({ status: 502, code: "bad_gateway", message: "Open-Meteo: 429" }),
      },
    });
    expect(failed).toMatchObject({ status: "failed", message: "Open-Meteo: 429" });
    const insufficient = state({
      drift: {
        scenario: {
          ...scenario,
          status: "insufficient_data",
          label: "недостаточно данных",
          reason: "нет данных ветра, волн или течений: повторите через минуту",
        },
        error: null,
      },
    });
    expect(insufficient).toMatchObject({
      status: "unavailable",
      label: "недостаточно данных",
      reason: "нет данных ветра, волн или течений: повторите через минуту",
    });
    const unreadable = state({ drift: { scenario: undefined, error: new Error("boom") } });
    expect(unreadable.status).toBe("failed");
    if (unreadable.status === "failed") unreadable.retry();
    expect(actions.reloadDrift).toHaveBeenCalled();
    expect(state({ analysis: { candidates: null, error: new Error("boom") } }).status).toBe(
      "failed",
    );
  });

  it("treats a cached empty result as missing zones", () => {
    expect(
      state({
        drift: {
          scenario: { ...scenario, status: "no_zones", reason: "в анализе нет зон детекции" },
          error: null,
        },
      }),
    ).toEqual({ status: "no-zones", reason: "в анализе нет зон детекции" });
  });
});
