import { z } from "zod";
import { apiRequest } from "./client";
import { bboxSchema, polygonSchema, positionSchema } from "./geojson";

export const DRIFT_STATUSES = ["scenario", "no_zones", "insufficient_data"] as const;

const estimateSchema = z.object({ value: z.number(), low: z.number(), high: z.number() });

const envelopeSchema = z.object({
  horizon_h: z.number().int(),
  median: positionSchema,
  polygon: polygonSchema,
  probability: z.number(),
  afloat: z.number(),
});

const beachingSchema = z.object({
  id: z.string(),
  name: z.string(),
  severity: z.enum(["alarm", "caution", "info"]),
  probability: estimateSchema,
  members: z.number().int(),
  window_h: z.tuple([z.number(), z.number()]),
  path: z.array(positionSchema),
  label_at: positionSchema.nullable(),
});

const sourceSchema = z.object({
  id: z.string(),
  name: z.string(),
  kind: z.string().nullable(),
  position: positionSchema.nullable(),
  probability: estimateSchema,
  members: z.number().int(),
  hours_back: z.number().nullable(),
});

const forecastSchema = z.object({
  candidate_id: z.string(),
  issued_at: z.string(),
  forcing: z.object({
    currents: z.string(),
    wind: z.string(),
    waves: z.string().nullable(),
    run_at: z.string(),
  }),
  windage_ratio: z.number(),
  origin: positionSchema,
  median_path: z.array(positionSchema),
  envelopes: z.array(envelopeSchema),
  beaching_risk: z.object({ segment: z.string(), probability: z.number() }).nullable(),
  hindcast_path: z.array(positionSchema),
  beached_by_hour: z.array(z.number()),
  beaching: z.array(beachingSchema),
  beaching_any: estimateSchema,
  sources: z.array(sourceSchema),
});

const runSchema = z.object({
  t0: z.string(),
  run_at: z.string(),
  issued_at: z.string(),
  ensemble_size: z.number().int(),
  windage_ratio: z.number(),
  windage_ratios: z.array(z.number()),
  wind_from_deg: z.number(),
  wind_speed_ms: z.number(),
  hours: z.number().int(),
  hindcast_hours: z.number().int(),
  currents: z.string(),
  wind: z.string(),
  waves: z.string().nullable(),
  model: z.string(),
});

const gridSchema = z.array(z.array(z.number().nullable()));

const currentFieldSchema = z.object({
  label: z.string(),
  time: z.string(),
  units: z.string(),
  bounds: bboxSchema,
  lons: z.array(z.number()),
  lats: z.array(z.number()),
  u: gridSchema,
  v: gridSchema,
  water: z.array(z.array(z.boolean())),
  typical_speed_ms: z.number(),
  mask: z.object({
    bounds: bboxSchema,
    rows: z.number().int(),
    cols: z.number().int(),
    row_order: z.literal("north_to_south"),
    water: z.string(),
    data: z.array(z.string()),
  }),
});

export const driftSchema = z.object({
  analysis_id: z.string(),
  model: z.string(),
  status: z.object({ status: z.enum(DRIFT_STATUSES), label: z.string() }),
  reason: z.string(),
  value_kind: z.string(),
  request: z.object({ hours: z.number().int(), hindcast_hours: z.number().int() }),
  computed_at: z.string(),
  zones: z.object({
    total: z.number().int(),
    computed: z.number().int(),
    limit: z.number().int(),
  }),
  run: runSchema.nullable(),
  current_field: currentFieldSchema.nullable(),
  forecasts: z.array(forecastSchema),
  messages: z.array(z.string()),
});

export type DriftResultStatus = (typeof DRIFT_STATUSES)[number];
export type DriftResponse = z.infer<typeof driftSchema>;
export type DriftForecastItem = z.infer<typeof forecastSchema>;
export type DriftRunItem = z.infer<typeof runSchema>;
export type DriftCurrentField = z.infer<typeof currentFieldSchema>;

const driftPath = (analysisId: string) => `/analyses/${encodeURIComponent(analysisId)}/drift`;

export const getDrift = (analysisId: string, signal?: AbortSignal) =>
  apiRequest(driftPath(analysisId), driftSchema, { signal });

export const createDrift = (analysisId: string) =>
  apiRequest(driftPath(analysisId), driftSchema, { method: "POST" });
