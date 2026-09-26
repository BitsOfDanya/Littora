import { describe, expect, it } from "vitest";
import { timelineCompareSchema, timelineSchema } from "./timeline";

const request = {
  bbox: [29.55, 43.49, 29.91, 43.67],
  date_from: "2024-05-18",
  date_to: "2024-06-17",
  aoi_id: "doors-west",
  target: "litter-visual",
};

const scene = {
  id: "S2B_T35TQJ_20240521T090227_L2A",
  aoi_id: "doors-west",
  collection: "sentinel-2-c1-l2a",
  platform: "S2B",
  processing_level: "L2A",
  acquired_at: "2024-05-21T09:08:07.919Z",
  mgrs_tile: "35TQJ",
  relative_orbit: 50,
  footprint: [28.2, 43.2, 29.9, 44.2],
  geometry: {
    type: "Polygon",
    coordinates: [
      [
        [28.2, 43.2],
        [29.9, 43.2],
        [29.9, 44.2],
        [28.2, 43.2],
      ],
    ],
  },
  area_coverage: 1,
  cloud_cover: 0.0274,
  valid_water_fraction: 0.9726,
  water_fraction: 0.6,
  sun_glint_risk: "moderate",
  sun_zenith_deg: 26.5,
  usability: "usable",
};

const analysis = {
  id: "0123456789abcdef",
  computed_at: "2026-09-26T08:38:40+00:00",
  window_days: 1,
  status: { status: "detected", label: "обнаружено" },
  detection: {
    status: "detected",
    label: "обнаружено",
    reason: "зон: 230, пикселей выше порога 0.16: 603",
    model: "raunet__marida_mixed__common",
    threshold: 0.159,
  },
  zone_count: 230,
  zones_limited: false,
  area_km2: 0.0603,
  probability_max: 0.9997,
  concentration: {
    status: "concentration_unavailable",
    label: "концентрация недоступна",
    reason: "район вне области полевых данных профилей",
    value: null,
    lower: null,
    upper: null,
    unit: "шт./км²",
  },
  quality: { usable: true, reasons: [], cloud: 0.03, water: 0.97 },
  layers: ["image", "mask", "probability"],
};

const run = {
  id: "90b23bb3f77b",
  status: "running",
  request,
  current_scene_id: scene.id,
  created_at: "2026-09-26T08:39:50+00:00",
  started_at: "2026-09-26T08:39:50+00:00",
  finished_at: null,
  message: null,
  total: 1,
  completed: 0,
  failed: 0,
  items: [
    {
      scene_id: scene.id,
      acquired_at: scene.acquired_at,
      state: "running",
      analysis_id: null,
      status: null,
      message: null,
    },
  ],
};

describe("timeline contract", () => {
  it("parses the series with analyses, changes and the active run", () => {
    const parsed = timelineSchema.parse({
      request,
      target: { key: "litter-visual", title: "Весь мусор, визуальный учёт" },
      models: { detector: "raunet__marida_mixed__common", concentration: "field-profiles" },
      value_kind: "detections",
      note: "Ряд детекций по пролётам Sentinel-2",
      summary: { passes: 2, usable: 2, analysed: 2, comparable: 2 },
      passes: [
        { scene, analysis, change: null },
        {
          scene: { ...scene, id: "S2A_T35TQJ_20240602T084613_L2A" },
          analysis: { ...analysis, id: "fedcba9876543210" },
          change: {
            before: {
              analysis_id: analysis.id,
              scene_id: scene.id,
              acquired_at: scene.acquired_at,
              status: "detected",
            },
            counts: { new: 4, persisting: 2, disappeared: 1, not_observed: 3 },
            area_km2: { new: 0.002, persisting: 0.001, disappeared: 0.0004, not_observed: 0.003 },
          },
        },
      ],
      run,
      limits: { default_passes: 6, max_passes: 12, max_range_days: 120, window_days: 1 },
    });
    expect(parsed.passes[1].change?.counts.new).toBe(4);
    expect(parsed.passes[1].change?.counts.not_observed).toBe(3);
    expect(parsed.run?.status).toBe("running");
  });

  it("rejects a series that claims to be something other than detections", () => {
    const result = timelineSchema.safeParse({ value_kind: "concentration" });
    expect(result.success).toBe(false);
  });

  it("parses comparable and blocked comparisons", () => {
    const refs = {
      before: { analysis_id: "a", scene_id: "s1", acquired_at: null, status: "detected" },
      after: { analysis_id: "b", scene_id: "s2", acquired_at: null, status: "insufficient_data" },
      value_kind: "detections",
    };
    expect(
      timelineCompareSchema.parse({ ...refs, comparable: false, reason: "нет данных" }).comparable,
    ).toBe(false);
    const full = timelineCompareSchema.parse({
      ...refs,
      comparable: true,
      reason: null,
      counts: { new: 1, persisting: 0, disappeared: 1, not_observed: 1 },
      area_km2: { new: 0.001, persisting: 0, disappeared: 0.001, not_observed: 0.001 },
      after_zones: { "zone-1": "new" },
      before_zones: { "zone-1": "disappeared", "zone-2": "not_observed" },
      tolerance_m: 20,
      method: "перекрытие контуров",
    });
    expect(full.before_zones?.["zone-2"]).toBe("not_observed");
  });
});
