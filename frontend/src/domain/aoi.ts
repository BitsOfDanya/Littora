import type { BBox, LngLat } from "./geo";

export type AoiGroup = "case" | "reference" | "russian-seas";

export type WaterLabelRank = "major" | "minor";

export type WaterLabel = {
  name: string;
  position: LngLat;
  rank: WaterLabelRank;
  minZoom?: number;
};

export type AoiSurvey = {
  source: string;
  dates: readonly string[];
  period: readonly [from: string, to: string];
  events: readonly string[];
};

export type AreaOfInterest = {
  id: string;
  name: string;
  seaName: string;
  country: string;
  group: AoiGroup;
  center: LngLat;
  zoom: number;
  bbox: BBox;
  sentinel2Tiles: readonly string[];
  rationale: string;
  datasets: readonly string[];
  waterLabels: readonly WaterLabel[];
  survey?: AoiSurvey;
};
