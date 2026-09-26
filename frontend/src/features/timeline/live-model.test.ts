import { describe, expect, it } from "vitest";
import type { SceneSummary } from "@/domain/scene";
import type { TimelinePass, TimelinePassAnalysis, TimelineRun } from "@/lib/api/timeline";
import { liveSeries, missingInPair, openUsable, passVerdict, runStateOf } from "./live-model";

function scene(id: string, day: string, usability: SceneSummary["usability"]): SceneSummary {
  return {
    id,
    aoiId: "doors-west",
    platform: "S2A",
    processingLevel: "L2A",
    acquiredAt: `${day}T08:58:16.000Z`,
    mgrsTile: "35TQJ",
    relativeOrbit: 107,
    footprint: [29, 43, 30, 44],
    cloudCover: usability === "usable" ? 0.02 : 0.7,
    validWaterFraction: 0.98,
    sunGlintRisk: "moderate",
    sunZenithDeg: 30,
    usability,
  };
}

function analysis(id: string, zones: number | null, area: number | null): TimelinePassAnalysis {
  return {
    id,
    computed_at: "2026-09-26T08:00:00+00:00",
    window_days: 1,
    status: {
      status: zones === null ? "insufficient_data" : zones ? "detected" : "not_detected",
      label: "",
    },
    detection: { status: "detected", label: "", reason: "", model: "m", threshold: 0.16 },
    zone_count: zones,
    zones_limited: false,
    retryable: false,
    area_km2: area,
    probability_max: zones ? 0.9 : null,
    concentration: {
      status: "concentration_unavailable",
      label: "концентрация недоступна",
      reason: null,
      value: null,
      lower: null,
      upper: null,
      unit: "шт./км²",
    },
    quality: null,
    layers: ["image"],
  };
}

const SCENES = [
  scene("d1", "2024-06-02", "usable"),
  scene("d2", "2024-06-05", "unusable"),
  scene("d3", "2024-06-07", "usable"),
  scene("d4", "2024-06-10", "partial"),
  scene("d5", "2024-06-12", "usable"),
];

function passes(entries: Record<string, TimelinePassAnalysis>): Map<string, TimelinePass> {
  return new Map(
    Object.entries(entries).map(([id, value]) => [
      id,
      { scene: {} as TimelinePass["scene"], analysis: value, change: null },
    ]),
  );
}

const LIVE = passes({
  d1: analysis("a1", 3, 0.012),
  d3: analysis("a3", 0, 0),
  d4: analysis("a4", null, null),
});

describe("live timeline model", () => {
  it("classifies passes without inventing values", () => {
    expect(passVerdict(null)).toBe("pending");
    expect(passVerdict(analysis("x", null, null))).toBe("insufficient");
    expect(passVerdict(analysis("x", 0, 0))).toBe("not-detected");
    expect(passVerdict(analysis("x", 2, 0.01))).toBe("detected");
  });

  it("plots only analysed passes, with zone area in square metres", () => {
    const series = liveSeries(SCENES, LIVE);
    expect(series.map((point) => [point.id, point.state, point.value])).toEqual([
      ["d1", "observed", 12_000],
      ["d3", "not-found", 0],
      ["d4", "cloudy", undefined],
    ]);
  });

  it("reports which dates of the pair still need analysis", () => {
    const pair = { a: SCENES[0], b: SCENES[4], aIndex: 0, bIndex: 4 };
    expect(missingInPair(pair, LIVE)).toEqual(["d5"]);
    expect(openUsable(SCENES, LIVE)).toBe(1);
  });

  it("reads a pass state from the run", () => {
    const run: TimelineRun = {
      id: "run-1",
      status: "running",
      request: {
        bbox: [29.55, 43.49, 29.91, 43.67],
        date_from: "2024-05-18",
        date_to: "2024-06-17",
        aoi_id: "doors-west",
        target: "litter-visual",
      },
      current_scene_id: "d5",
      created_at: "2026-09-26T08:00:00+00:00",
      started_at: "2026-09-26T08:00:00+00:00",
      finished_at: null,
      message: null,
      total: 1,
      completed: 0,
      failed: 0,
      items: [
        {
          scene_id: "d5",
          acquired_at: "2024-06-12T08:58:16.000Z",
          state: "running",
          analysis_id: null,
          status: null,
          message: null,
        },
      ],
    };
    expect(runStateOf(run, "d5")).toBe("running");
    expect(runStateOf(run, "d1")).toBeNull();
    expect(runStateOf(null, "d1")).toBeNull();
  });
});
