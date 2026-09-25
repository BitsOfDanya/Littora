import { describe, expect, it } from "vitest";
import { analysisListSchema, analysisSchema } from "./analyses";
import { observationCollectionSchema } from "./case";
import { sceneListSchema, toSceneSummary } from "./scenes";

const observation = {
  type: "Feature",
  id: "MPL-0904",
  geometry: { type: "Point", coordinates: [29.62, 43.61] },
  properties: {
    sample_id: "MPL-0904",
    event_id: "S4:DOORS3:T1",
    source_id: "S4_BLACK_SEA_DOORS3",
    source_short: "DOORS3",
    source_doi: "",
    source_license: "CC BY 4.0",
    region: "Black Sea",
    sea_area: "western Black Sea",
    sampling_method: "ship-based visual transect, floating macro litter >2.5 cm",
    platform: "R/V",
    measurement_profile: "S4_visual_GT2_5",
    target_scope: "all_litter",
    material: "all",
    size_class: ">2.5 cm",
    date: "2024-06-02",
    time_start: null,
    time_end: null,
    position_role: "transect_start",
    value_kind: "measurement",
    concentration: 192.54,
    recomputed: null,
    unit: "шт./км²",
    items: null,
    area_km2: null,
    check: "published_only",
    check_label: "только опубликованное значение",
    target_key: "litter-visual",
    decision: "accepted",
    reason_code: "accepted",
    reason: "принято",
    quality_flags: [],
    pair_decision: "accepted",
    pair_reason: "пара принята",
    pair_scene_id: "S2A_T35TQJ_20240602T084613_L2A",
    delta_days: 0,
    synchronous: true,
  },
};

const analysis = {
  id: "4d3f162a2db603d3",
  pipeline_version: "1",
  computed_at: "2026-09-25T14:02:11+00:00",
  request: {
    aoi_id: "doors-west",
    aoi_name: "Разрезы T1–T2",
    bbox: [29.45, 43.45, 30, 43.72],
    date: "2024-06-02",
    window_days: 1,
    scene_id: "S2A_T35TQJ_20240602T084613_L2A",
    target: "litter-visual",
  },
  area: {
    type: "Polygon",
    coordinates: [
      [
        [30, 43.45],
        [30, 43.72],
        [29.45, 43.72],
        [29.45, 43.45],
        [30, 43.45],
      ],
    ],
  },
  target: {
    key: "litter-visual",
    title: "Плавающий макромусор, визуальный учёт с судна",
    material: "весь плавающий мусор",
    size_class: "от 2 см",
    unit: "шт./км²",
  },
  scene: {
    id: "S2A_T35TQJ_20240602T084613_L2A",
    collection: "sentinel-2-c1-l2a",
    platform: "S2A",
    acquired_at: "2024-06-02T08:46:13.024Z",
    cloud_cover: 0.4,
    tile: "35TQJ",
    relative_orbit: 107,
    sun_elevation: 64.1,
    water_percentage: 71.2,
    footprint: [28.5, 43.2, 30.1, 44.2],
  },
  quality: {
    pixels: 402000,
    water: 1,
    cloud: 0,
    shadow: 0,
    snow: 0,
    land: 0,
    nodata: 0,
    other: 0,
    bright_water: 0.002,
    usable: true,
    reasons: [],
  },
  layers: {
    image: {
      file: "image.png",
      corners: [
        [29.45, 43.72],
        [30, 43.72],
        [30, 43.45],
        [29.45, 43.45],
      ],
    },
  },
  status: { status: "insufficient_data", label: "недостаточно данных" },
  detection: {
    status: "insufficient_data",
    label: "недостаточно данных",
    reason: "модель детектора не подключена",
    model: null,
    zones: [],
  },
  concentration: {
    status: "concentration_unavailable",
    label: "концентрация недоступна",
    reason: "модель концентрации не подключена; перенос на снимки не подтверждён",
    model: null,
    value: null,
    lower: null,
    upper: null,
    unit: "шт./км²",
    value_kind: "model_estimate",
  },
  observations: [observation],
  messages: [],
};

describe("API contracts", () => {
  it("accepts an analysis result as the backend stores it", () => {
    const parsed = analysisSchema.parse(analysis);
    expect(parsed.observations[0].properties.synchronous).toBe(true);
    expect(parsed.layers.mask).toBeUndefined();
  });

  it("accepts the saved request listing", () => {
    const listing = analysisListSchema.parse({
      items: [
        {
          id: analysis.id,
          computed_at: analysis.computed_at,
          request: analysis.request,
          scene_id: analysis.scene.id,
          scene_acquired_at: analysis.scene.acquired_at,
          status: analysis.status,
          concentration: { status: "concentration_unavailable", label: "концентрация недоступна" },
          observations: 1,
        },
      ],
    });
    expect(listing.items).toHaveLength(1);
  });

  it("accepts field observations with point and strip geometry", () => {
    const strip = {
      ...observation,
      id: "MPL-0001",
      geometry: {
        type: "LineString",
        coordinates: [
          [7.1, 54.1],
          [7.3, 54.2],
        ],
      },
      properties: { ...observation.properties, sample_id: "MPL-0001" },
    };
    const parsed = observationCollectionSchema.parse({
      type: "FeatureCollection",
      features: [observation, strip],
    });
    expect(parsed.features.map((feature) => feature.geometry.type)).toEqual([
      "Point",
      "LineString",
    ]);
  });

  it("maps catalog scenes onto the scene summary used by the rail", () => {
    const list = sceneListSchema.parse({
      items: [
        {
          id: "S2A_T35TQJ_20240602T084613_L2A",
          aoi_id: "doors-west",
          collection: "sentinel-2-c1-l2a",
          platform: "S2A",
          processing_level: "L2A",
          acquired_at: "2024-06-02T08:46:13.024Z",
          mgrs_tile: "35TQJ",
          relative_orbit: null,
          footprint: [28.5, 43.2, 30.1, 44.2],
          geometry: null,
          area_coverage: 1,
          cloud_cover: 0.004,
          valid_water_fraction: 0.996,
          water_fraction: 0.71,
          sun_glint_risk: "high",
          sun_zenith_deg: 25.9,
          usability: "usable",
        },
      ],
    });
    const summary = toSceneSummary(list.items[0], "doors-west");
    expect(summary.mgrsTile).toBe("35TQJ");
    expect(summary.relativeOrbit).toBeNull();
    expect(summary.areaCoverage).toBe(1);
    expect(summary.aoiId).toBe("doors-west");
  });
});
