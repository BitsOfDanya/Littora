import { describe, expect, it } from "vitest";
import type { SceneSummary } from "@/domain/scene";
import { analysisListSchema, analysisSchema, conditionsSchema } from "@/lib/api/analyses";
import { defaultScene } from "./use-analysis";
import {
  declutterLabels,
  cropPixel,
  cropView,
  findCurrentMatch,
  imageFrame,
  toFrameMeters,
  toRealZones,
  zoneBounds,
  zoneColor,
  zoneLabel,
  zoneStrength,
} from "./zones";

const square: { type: "Polygon"; coordinates: [number, number][][] } = {
  type: "Polygon",
  coordinates: [
    [
      [37.8, 44.7],
      [37.801, 44.7],
      [37.801, 44.701],
      [37.8, 44.701],
      [37.8, 44.7],
    ],
  ],
};

const corners: [number, number][] = [
  [37.7, 44.8],
  [38.0, 44.8],
  [38.0, 44.6],
  [37.7, 44.6],
];

function scene(id: string, day: string, usability: SceneSummary["usability"]): SceneSummary {
  return {
    id,
    aoiId: "novorossiysk",
    platform: "S2B",
    processingLevel: "L2A",
    acquiredAt: `${day}T08:37:00Z`,
    mgrsTile: "37TDK",
    relativeOrbit: 7,
    footprint: [37, 44, 38, 45],
    areaCoverage: 1,
    cloudCover: usability === "usable" ? 0.01 : 0.7,
    validWaterFraction: 0.9,
    sunGlintRisk: "moderate",
    sunZenithDeg: 40,
    usability,
  };
}

describe("real detector zones", () => {
  const [first, second] = toRealZones([
    {
      id: "zone-1",
      geometry: square,
      pixels: 5,
      area_km2: 0.0005,
      probability_max: 0.97,
      probability_mean: 0.8,
      centroid: [37.8005, 44.7005],
      scl: { water: 0.8, cloud: 0.2 },
    },
    { geometry: { type: "Point", coordinates: [37.9, 44.65] }, probability_max: 0.2 },
  ]);

  it("keeps the measured fields and never invents missing ones", () => {
    expect(first).toMatchObject({ id: "zone-1", rank: 1, pixels: 5, areaM2: 500 });
    expect(first.scl).toEqual({ water: 0.8, cloud: 0.2 });
    expect(second).toMatchObject({ id: "zone-2", geometry: null, areaM2: null, pixels: null });
    expect(zoneLabel(first)).toBe("zone-1 · 0,97");
    expect(zoneBounds(first)).toEqual([37.8, 44.7, 37.801, 44.701]);
  });

  it("colours zones from the threshold up", () => {
    expect(zoneStrength(0.16, 0.16)).toBe(0);
    expect(zoneStrength(1, 0.16)).toBe(1);
    expect(zoneStrength(null, 0.16)).toBe(0);
    expect(zoneColor(0.16, 0.16)).toEqual([255, 214, 102, 255]);
    expect(zoneColor(1, 0.16)).toEqual([200, 30, 60, 255]);
  });
});

describe("zone labels", () => {
  const zones = toRealZones([
    { id: "zone-1", centroid: [37.8, 44.7], probability_max: 0.99 },
    { id: "zone-2", centroid: [37.8001, 44.7], probability_max: 0.9 },
    { id: "zone-3", centroid: [37.9, 44.65], probability_max: 0.5 },
  ]);

  it("drops labels that would overlap and keeps the selected one", () => {
    const ids = (list: readonly { id: string }[]) => list.map((zone) => zone.id);
    expect(ids(declutterLabels(zones, 11, [null, null], 25))).toEqual(["zone-1", "zone-3"]);
    expect(ids(declutterLabels(zones, 11, ["zone-2", null], 25))).toEqual(["zone-2", "zone-3"]);
    expect(ids(declutterLabels(zones, 21, [null, null], 25))).toEqual([
      "zone-1",
      "zone-2",
      "zone-3",
    ]);
    expect(ids(declutterLabels(zones, 11, [null, null], 1))).toEqual(["zone-1"]);
  });
});

describe("zone crop geometry", () => {
  const frame = imageFrame({ corners });

  it("maps image corners onto the frame in metres", () => {
    const [left, top] = toFrameMeters(frame, [37.7, 44.8]);
    expect(Math.abs(left) + Math.abs(top)).toBe(0);
    const [x, y] = toFrameMeters(frame, [38.0, 44.6]);
    expect(x).toBeCloseTo(frame.widthM, 3);
    expect(y).toBeCloseTo(frame.heightM, 3);
    expect(frame.heightM).toBeGreaterThan(22_000);
  });

  it("centres the zone and keeps a minimum extent", () => {
    const view = cropView(frame, square.coordinates[0], 320, 196, 400);
    expect(view).not.toBeNull();
    if (!view) return;
    expect(view.widthM).toBeGreaterThanOrEqual(400);
    const [cx, cy] = cropPixel(view, frame, [37.8005, 44.7005]);
    expect(cx).toBeCloseTo(160, 0);
    expect(cy).toBeCloseTo(98, 0);
    expect(cropView(frame, [], 320, 196, 400)).toBeNull();
  });
});

describe("saved results", () => {
  it("never picks a stale result as the current one", () => {
    const items = [
      { id: "old", stale: true },
      { id: "new", stale: false },
    ];
    expect(findCurrentMatch(items, () => true)?.id).toBe("new");
    expect(findCurrentMatch([{ id: "old", stale: true }], () => true)).toBeNull();
  });

  it("reads stale flags, fingerprints and zone counts from the API", () => {
    const listing = analysisListSchema.parse({
      items: [
        {
          id: "0123456789abcdef",
          computed_at: "2026-09-26T08:00:00+00:00",
          request: {
            aoi_id: "novorossiysk",
            aoi_name: "Новороссийск",
            bbox: [37.7466, 44.6, 37.9998, 44.78],
            date: "2025-09-04",
            window_days: 1,
            scene_id: null,
            target: "litter-visual",
          },
          scene_id: "S2B_T37TDK_20250904T083254_L2A",
          scene_acquired_at: "2025-09-04T08:37:37.987Z",
          status: { status: "detected", label: "обнаружено" },
          concentration: { status: "concentration_unavailable", label: "концентрация недоступна" },
          observations: 0,
          zones: 42,
          stale: true,
        },
      ],
    });
    expect(listing.items[0]).toMatchObject({ zones: 42, stale: true });
    expect(analysisSchema.shape.stale.parse(undefined)).toBe(false);
    const conditions = conditionsSchema.parse({
      analysis_id: "0123456789abcdef",
      acquired_at: "2025-09-04T08:37:37.987Z",
      at: "2025-09-04T09:00:00Z",
      point: [37.87, 44.69],
      wind: { speed_ms: 4.2, from_deg: 310, source: "Open-Meteo Archive · ERA5 0,25°" },
      waves: null,
      messages: ["у Open-Meteo нет данных о волнении на 2025-09-04T09:00 UTC"],
    });
    expect(conditions.wind?.speed_ms).toBe(4.2);
  });
});

describe("default scene", () => {
  const scenes = [
    scene("a", "2025-08-20", "usable"),
    scene("b", "2025-08-30", "usable"),
    scene("c", "2025-09-04", "unusable"),
  ];

  it("opens the latest usable pass when there is no ship survey", () => {
    expect(defaultScene(scenes, null)?.id).toBe("b");
    expect(defaultScene([scenes[2]], null)).toBeUndefined();
  });

  it("keeps the survey day for case areas", () => {
    expect(defaultScene(scenes, "2025-09-04")?.id).toBe("c");
  });
});
