import type { BBox } from "./geo";
import type { ProcessingLevel } from "./sentinel2";

export type SentinelPlatform = "S2A" | "S2B" | "S2C";

export type SceneUsability = "usable" | "partial" | "unusable";

export type SceneSummary = {
  id: string;
  aoiId: string;
  platform: SentinelPlatform;
  processingLevel: ProcessingLevel;
  acquiredAt: string;
  mgrsTile: string;
  relativeOrbit: number | null;
  footprint: BBox;
  outline?: GeoJSON.Polygon | GeoJSON.MultiPolygon | null;
  areaCoverage?: number;
  cloudCover: number;
  validWaterFraction: number;
  sunGlintRisk: "low" | "moderate" | "high";
  sunZenithDeg: number | null;
  usability: SceneUsability;
};
