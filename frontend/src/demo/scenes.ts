import type { LngLat } from "@/domain/geo";
import type { SceneSummary, SceneUsability, SentinelPlatform } from "@/domain/scene";
import { DEMO_AOI_ID } from "./scenario";

export const DEMO_SCENE_TILE = "16PCC";
export const DEMO_RELATIVE_ORBIT = 97;
export const DEMO_PROCESSING_BASELINE = "N0511";

type SceneSeed = readonly [
  date: string,
  time: string,
  platform: SentinelPlatform,
  cloud: number,
  glint: SceneSummary["sunGlintRisk"],
];

const SEEDS: readonly SceneSeed[] = [
  ["2026-07-05", "16:05:31", "S2B", 0.12, "low"],
  ["2026-07-10", "16:05:29", "S2C", 0.64, "low"],
  ["2026-07-15", "16:05:41", "S2B", 0.31, "moderate"],
  ["2026-07-20", "16:05:19", "S2C", 0.88, "low"],
  ["2026-07-25", "16:05:37", "S2B", 0.07, "moderate"],
  ["2026-07-30", "16:05:22", "S2C", 0.41, "high"],
  ["2026-08-04", "16:05:44", "S2B", 0.95, "low"],
  ["2026-08-09", "16:05:18", "S2C", 0.18, "low"],
  ["2026-08-14", "16:05:33", "S2B", 0.52, "moderate"],
  ["2026-08-19", "16:05:26", "S2C", 0.09, "low"],
  ["2026-08-24", "16:05:40", "S2B", 0.77, "low"],
  ["2026-08-29", "16:05:21", "S2C", 0.23, "moderate"],
  ["2026-09-03", "16:05:35", "S2B", 0.14, "low"],
  ["2026-09-08", "16:05:17", "S2C", 0.69, "high"],
  ["2026-09-13", "16:05:38", "S2B", 0.34, "low"],
  ["2026-09-18", "16:05:24", "S2C", 0.06, "low"],
];

export const DEMO_TILE_FOOTPRINT: readonly LngLat[] = [
  [-88.8633, 15.369],
  [-87.8405, 15.3752],
  [-87.8446, 16.3677],
  [-88.8724, 16.3611],
];

function usabilityOf(cloudCover: number): SceneUsability {
  if (cloudCover < 0.3) return "usable";
  if (cloudCover < 0.7) return "partial";
  return "unusable";
}

function sceneId(date: string, time: string, platform: SentinelPlatform): string {
  const stamp = `${date.replaceAll("-", "")}T${time.replaceAll(":", "")}`;
  const orbit = `R${String(DEMO_RELATIVE_ORBIT).padStart(3, "0")}`;
  return `${platform}_MSIL2A_${stamp}_${DEMO_PROCESSING_BASELINE}_${orbit}_T${DEMO_SCENE_TILE}_${date.replaceAll("-", "")}T194512`;
}

function footprintBBox(): SceneSummary["footprint"] {
  const lngs = DEMO_TILE_FOOTPRINT.map(([lng]) => lng);
  const lats = DEMO_TILE_FOOTPRINT.map(([, lat]) => lat);
  return [Math.min(...lngs), Math.min(...lats), Math.max(...lngs), Math.max(...lats)];
}

export const DEMO_SCENES: readonly SceneSummary[] = SEEDS.map(
  ([date, time, platform, cloud, glint], index) => ({
    id: sceneId(date, time, platform),
    aoiId: DEMO_AOI_ID,
    platform,
    processingLevel: "L2A",
    acquiredAt: `${date}T${time}Z`,
    mgrsTile: DEMO_SCENE_TILE,
    relativeOrbit: DEMO_RELATIVE_ORBIT,
    footprint: footprintBBox(),
    cloudCover: cloud,
    validWaterFraction: Math.max(0, Math.round((1 - cloud * 1.08) * 100) / 100),
    sunGlintRisk: glint,
    sunZenithDeg: 28 + (index % 5) * 1.7,
    usability: usabilityOf(cloud),
  }),
);

export const DEMO_LATEST_SCENE = DEMO_SCENES[DEMO_SCENES.length - 1];

export type PlannedPass = { at: string; platform: SentinelPlatform };

export const DEMO_PLANNED_PASSES: readonly PlannedPass[] = [
  { at: "2026-09-26T16:10:00Z", platform: "S2B" },
  { at: "2026-10-01T16:05:00Z", platform: "S2C" },
  { at: "2026-10-06T16:10:00Z", platform: "S2B" },
];

export function findDemoScene(id: string): SceneSummary | undefined {
  return DEMO_SCENES.find((scene) => scene.id === id);
}
