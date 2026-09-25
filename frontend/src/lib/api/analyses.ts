import { z } from "zod";
import type { BBox } from "@/domain/geo";
import { apiRequest, apiUrl, withQuery } from "./client";
import { observationSchema } from "./case";
import { bboxSchema, geometrySchema, polygonSchema, positionSchema } from "./geojson";

export const RESULT_STATUSES = [
  "detected",
  "not_detected",
  "insufficient_data",
  "research_estimate",
  "concentration_unavailable",
] as const;

export const resultStatusSchema = z.enum(RESULT_STATUSES);

const statusSchema = z.object({ status: resultStatusSchema, label: z.string() });

const layerSchema = z.object({
  file: z.string(),
  corners: z.array(positionSchema).length(4),
});

export const qualitySchema = z.object({
  pixels: z.number(),
  water: z.number(),
  cloud: z.number(),
  shadow: z.number(),
  snow: z.number(),
  land: z.number(),
  nodata: z.number(),
  other: z.number(),
  bright_water: z.number().nullable(),
  usable: z.boolean(),
  reasons: z.array(z.string()),
});

export const analysisSceneSchema = z.object({
  id: z.string(),
  collection: z.string(),
  platform: z.string(),
  acquired_at: z.string(),
  cloud_cover: z.number().nullable(),
  tile: z.string(),
  relative_orbit: z.number().nullable(),
  sun_elevation: z.number().nullable(),
  water_percentage: z.number().nullable(),
  footprint: bboxSchema,
});

export const zoneSchema = z.looseObject({
  id: z.string().optional(),
  geometry: geometrySchema.nullable().optional(),
  status_label: z.string().optional(),
  concentration: z.number().nullable().optional(),
  lower: z.number().nullable().optional(),
  upper: z.number().nullable().optional(),
});

export const analysisSchema = z.object({
  id: z.string(),
  pipeline_version: z.string(),
  computed_at: z.string(),
  request: z.object({
    aoi_id: z.string().nullable(),
    aoi_name: z.string().nullable(),
    bbox: bboxSchema,
    date: z.string(),
    window_days: z.number().int(),
    scene_id: z.string().nullable(),
    target: z.string(),
  }),
  area: polygonSchema,
  target: z.object({
    key: z.string(),
    title: z.string(),
    material: z.string(),
    size_class: z.string(),
    unit: z.string(),
  }),
  scene: analysisSceneSchema.nullable(),
  quality: qualitySchema.nullable(),
  layers: z.object({ image: layerSchema.optional(), mask: layerSchema.optional() }),
  status: statusSchema,
  detection: statusSchema.extend({
    reason: z.string(),
    model: z.string().nullable(),
    zones: z.array(zoneSchema),
  }),
  concentration: statusSchema.extend({
    reason: z.string(),
    model: z.string().nullable(),
    value: z.number().nullable(),
    lower: z.number().nullable(),
    upper: z.number().nullable(),
    unit: z.string(),
    value_kind: z.string(),
  }),
  observations: z.array(observationSchema),
  messages: z.array(z.string()),
});

export const analysisListItemSchema = z.object({
  id: z.string(),
  computed_at: z.string(),
  request: analysisSchema.shape.request,
  scene_id: z.string().nullable(),
  scene_acquired_at: z.string().nullable(),
  status: statusSchema,
  concentration: statusSchema,
  observations: z.number().int(),
});

export const analysisListSchema = z.object({ items: z.array(analysisListItemSchema) });

export type ResultStatus = z.infer<typeof resultStatusSchema>;
export type Analysis = z.infer<typeof analysisSchema>;
export type AnalysisQuality = z.infer<typeof qualitySchema>;
export type AnalysisListItem = z.infer<typeof analysisListItemSchema>;
export type AnalysisZone = z.infer<typeof zoneSchema>;

export type AnalysisCreate = {
  bbox: BBox;
  date: string;
  window_days: number;
  aoi_id?: string | null;
  aoi_name?: string | null;
  scene_id?: string | null;
  target?: string | null;
};

export type AnalysisFilters = {
  status?: ResultStatus | null;
  aoiId?: string | null;
  dateFrom?: string | null;
  dateTo?: string | null;
};

export type AnalysisFile = "image.png" | "mask.png" | "export.geojson" | "export.csv";

export const ANALYSIS_ID_PATTERN = /^[0-9a-f]{16}$/;

export const createAnalysis = (body: AnalysisCreate) =>
  apiRequest("/analyses", analysisSchema, { method: "POST", body });

export const getAnalysis = (id: string, signal?: AbortSignal) =>
  apiRequest(`/analyses/${encodeURIComponent(id)}`, analysisSchema, { signal });

export const listAnalyses = (filters: AnalysisFilters, signal?: AbortSignal) =>
  apiRequest(
    withQuery("/analyses", {
      status: filters.status,
      aoi_id: filters.aoiId,
      date_from: filters.dateFrom,
      date_to: filters.dateTo,
    }),
    analysisListSchema,
    { signal },
  ).then((list) => list.items);

export const analysisFileUrl = (id: string, file: AnalysisFile) =>
  apiUrl(`/analyses/${encodeURIComponent(id)}/${file}`);
