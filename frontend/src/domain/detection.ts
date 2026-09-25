import type { LngLat } from "./geo";
import type { Estimate } from "./measurement";
import type { Sentinel2BandId } from "./sentinel2";

export type ConfidenceClass = "likely" | "possible" | "low";

export type ReviewStatus =
  | "unreviewed"
  | "needs_survey"
  | "confirmed_litter"
  | "other_material"
  | "natural"
  | "nothing_found";

export type SurveyPriority = "high" | "medium" | "low";

export type LookAlike =
  "sargassum" | "foam" | "ship_wake" | "cloud_edge" | "sun_glint" | "turbid_water";

export type BandReflectance = {
  band: Sentinel2BandId;
  reflectance: number;
};

export type SpectralSignature = {
  candidate: readonly BandReflectance[];
  surroundingWater: readonly BandReflectance[];
  indices: { fdi: number; ndvi: number; fai: number };
};

export type ChangeSincePrevious = {
  previousSceneId: string;
  previousObservedAt: string;
  areaDeltaRatio: number;
  coverageDeltaPoints: number;
  displacementM: number;
};

export type DebrisCandidate = {
  id: string;
  aoiId: string;
  sceneId: string;
  observedAt: string;
  geometry: GeoJSON.Polygon;
  centroid: LngLat;
  shape: "windrow" | "patch";
  lengthM: number;
  areaM2: number;
  pixelCount: number;
  coverage: Estimate;
  confidence: { class: ConfidenceClass; score: number };
  priority: SurveyPriority;
  status: ReviewStatus;
  change: ChangeSincePrevious | null;
  persistence: { detectedIn: number; usablePasses: number };
  lookAlikes: readonly LookAlike[];
  distanceToCoastM: number;
  spectrum: SpectralSignature;
  model: { name: string; version: string };
};
