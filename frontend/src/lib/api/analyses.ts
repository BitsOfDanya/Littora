import { z } from "zod";
import type { BBox } from "@/domain/geo";
import { apiRequest, apiUpload, apiUrl, withQuery } from "./client";
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
  pixels: z.number().optional(),
  area_km2: z.number().optional(),
  probability_max: z.number().optional(),
  probability_mean: z.number().optional(),
  centroid: positionSchema.optional(),
  concentration: z.number().nullable().optional(),
  lower: z.number().nullable().optional(),
  upper: z.number().nullable().optional(),
  scl: z.record(z.string(), z.number()).optional(),
  flags: z
    .array(z.object({ kind: z.string(), label: z.string(), evidence: z.array(z.string()) }))
    .optional(),
  stability: z.object({ agreement: z.number(), views: z.number() }).nullable().optional(),
  coverage: z
    .object({
      mean: z.number(),
      low: z.number().nullable(),
      high: z.number().nullable(),
      area_m2: z.number().nullable(),
      area_m2_low: z.number().nullable(),
      area_m2_high: z.number().nullable(),
    })
    .nullable()
    .optional(),
});

export const analysisSchema = z.object({
  id: z.string(),
  pipeline_version: z.string(),
  retryable: z.boolean().default(false),
  models: z
    .object({ detector: z.string().nullable(), concentration: z.string().nullable() })
    .optional(),
  stale: z.boolean().default(false),
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
  layers: z.object({
    image: layerSchema.optional(),
    mask: layerSchema.optional(),
    probability: layerSchema.optional(),
    false_color: layerSchema.optional(),
    fdi: layerSchema.optional(),
    ndvi: layerSchema.optional(),
    coverage: layerSchema.optional(),
    anomalies: layerSchema.optional(),
  }),
  timings: z.record(z.string(), z.number()).optional(),
  upload: z
    .object({
      kind: z.enum(["sentinel2", "visible"]),
      bands: z.number().int(),
      anomalies: z.array(
        z.object({
          id: z.string(),
          centroid: positionSchema,
          pixels: z.number().int(),
          contrast: z.number(),
        }),
      ),
    })
    .optional(),
  status: statusSchema,
  detection: statusSchema.extend({
    reason: z.string(),
    model: z.string().nullable(),
    threshold: z.number().nullable().optional(),
    zones: z.array(zoneSchema),
  }),
  concentration: statusSchema.extend({
    reason: z.string(),
    model: z.string().nullable(),
    value: z.number().nullable(),
    lower: z.number().nullable(),
    upper: z.number().nullable(),
    profile: z.string().nullable().optional(),
    coverage: z.number().nullable().optional(),
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
  zones: z.number().int().optional(),
  stale: z.boolean().default(false),
});

export const analysisListSchema = z.object({ items: z.array(analysisListItemSchema) });

const windReadingSchema = z.object({
  speed_ms: z.number(),
  from_deg: z.number(),
  source: z.string(),
});

const wavesReadingSchema = z.object({
  height_m: z.number(),
  period_s: z.number().nullable().optional(),
  from_deg: z.number().nullable().optional(),
  source: z.string(),
});

export const conditionsSchema = z.object({
  analysis_id: z.string(),
  acquired_at: z.string(),
  at: z.string(),
  point: positionSchema,
  wind: windReadingSchema.nullable(),
  waves: wavesReadingSchema.nullable(),
  messages: z.array(z.string()),
});

export type ResultStatus = z.infer<typeof resultStatusSchema>;
export type Analysis = z.infer<typeof analysisSchema>;
export type AnalysisQuality = z.infer<typeof qualitySchema>;
export type AnalysisListItem = z.infer<typeof analysisListItemSchema>;
export type AnalysisZone = z.infer<typeof zoneSchema>;
export type AnalysisConditions = z.infer<typeof conditionsSchema>;
export type AnalysisLayer = z.infer<typeof layerSchema>;

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

export type AnalysisFile =
  | "image.png"
  | "mask.png"
  | "probability.png"
  | "export.geojson"
  | "export.csv"
  | "layers/false_color.png"
  | "layers/fdi.png"
  | "layers/ndvi.png"
  | "layers/coverage.png"
  | "layers/anomalies.png";

export const ANALYSIS_ID_PATTERN = /^[0-9a-f]{16}$/;

export const analysisRunningSchema = z.object({
  id: z.string(),
  state: z.literal("running"),
  started_at: z.string(),
  elapsed_s: z.number(),
  scene: analysisSceneSchema.nullable(),
});

const createdSchema = z.union([analysisRunningSchema, analysisSchema]);

export type AnalysisRunning = z.infer<typeof analysisRunningSchema>;

const POLL_DELAY_MS = 1_500;

const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function createAnalysis(body: AnalysisCreate): Promise<Analysis> {
  for (;;) {
    const created = await apiRequest("/analyses", createdSchema, { method: "POST", body });
    if (!("state" in created)) return created;
    await pause(POLL_DELAY_MS);
  }
}

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

export const getAnalysisConditions = (id: string, signal?: AbortSignal) =>
  apiRequest(`/analyses/${encodeURIComponent(id)}/conditions`, conditionsSchema, { signal });

export function analysisRequestOf(analysis: Pick<Analysis, "request">): AnalysisCreate {
  const { request } = analysis;
  return {
    bbox: request.bbox,
    date: request.date,
    window_days: request.window_days,
    aoi_id: request.aoi_id,
    aoi_name: request.aoi_name,
    scene_id: request.scene_id,
    target: request.target,
  };
}

export const analysisFileUrl = (id: string, file: AnalysisFile) =>
  apiUrl(`/analyses/${encodeURIComponent(id)}/${file}`);

export const pixelSchema = z.object({
  inside: z.boolean(),
  lon: z.number(),
  lat: z.number(),
  row: z.number().int().optional(),
  col: z.number().int().optional(),
  probability: z.number().nullable().optional(),
  threshold: z.number().optional(),
  above_threshold: z.boolean().optional(),
  fdi: z.number().nullable().optional(),
  ndvi: z.number().nullable().optional(),
  coverage: z.number().nullable().optional(),
  scl: z.object({ code: z.number().int(), label: z.string() }).optional(),
  reflectance: z.record(z.string(), z.number().nullable()).optional(),
  zone_id: z.string().nullable().optional(),
});

export type PixelValues = z.infer<typeof pixelSchema>;

export const getPixel = (id: string, lon: number, lat: number, signal?: AbortSignal) =>
  apiRequest(
    `/analyses/${encodeURIComponent(id)}/pixel?lon=${lon.toFixed(6)}&lat=${lat.toFixed(6)}`,
    pixelSchema,
    { signal },
  );

const estimateStatusSchema = z.object({ status: z.string(), label: z.string() });

export const targetEstimatesSchema = z.object({
  analysis_id: z.string(),
  date: z.string(),
  targets: z.array(
    z.object({
      key: z.string(),
      title: z.string(),
      material: z.string(),
      size_class: z.string(),
      profiles: z.array(z.string()),
      selected: z.boolean(),
      status: estimateStatusSchema,
      reason: z.string(),
      value: z.number().nullable(),
      lower: z.number().nullable(),
      upper: z.number().nullable(),
      profile: z.string().nullable(),
      unit: z.string(),
    }),
  ),
});

export type TargetEstimates = z.infer<typeof targetEstimatesSchema>;

export const getTargetEstimates = (id: string, signal?: AbortSignal) =>
  apiRequest(`/analyses/${encodeURIComponent(id)}/targets`, targetEstimatesSchema, { signal });

const domainFeatureSchema = z.object({
  type: z.literal("Feature"),
  geometry: geometrySchema,
  properties: z.object({
    profile: z.string(),
    target: z.string(),
    model: z.string(),
    value: z.number(),
    lower: z.number(),
    upper: z.number(),
    max_distance_km: z.number(),
    season: z.string(),
    points: z.number().int(),
  }),
});

export const domainCollectionSchema = z.object({
  type: z.literal("FeatureCollection"),
  features: z.array(domainFeatureSchema),
});

export type ConcentrationDomain = z.infer<typeof domainFeatureSchema>;

export const getConcentrationDomains = (signal?: AbortSignal) =>
  apiRequest("/concentration/domains", domainCollectionSchema, { signal });

export type UploadOptions = { name: string; bbox: BBox | null; date: string | null };

export const uploadImage = (file: Blob, options: UploadOptions) =>
  apiUpload(
    withQuery("/uploads", {
      name: options.name.slice(0, 120),
      bbox: options.bbox ? options.bbox.map((value) => value.toFixed(5)).join(",") : null,
      date: options.date,
    }),
    file,
    analysisSchema,
  );
