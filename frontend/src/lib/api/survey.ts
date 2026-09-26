import { z } from "zod";
import { apiRequest } from "./client";
import { positionSchema } from "./geojson";

export const SURVEY_STATUSES = ["estimate", "no_zones", "insufficient_data"] as const;

export const SURVEY_METHODS = ["vessel", "uav", "tasking"] as const;

export const URGENCY_LEVELS = ["high", "medium", "low", "unknown"] as const;

const componentSchema = z.number().nullable();

const componentsSchema = z.object({
  confidence: componentSchema,
  coverage: componentSchema,
  persistence: componentSchema,
  drift_risk: componentSchema,
  uncertainty: componentSchema,
  accessibility: componentSchema,
});

const beachingSchema = z.object({
  name: z.string(),
  severity: z.string(),
  probability: z.number(),
  window_h: z.tuple([z.number(), z.number()]),
});

const targetSchema = z.object({
  id: z.string(),
  rank: z.number().int(),
  score: z.number(),
  zone_ids: z.array(z.string()),
  lead_zone: z.string(),
  position: positionSchema,
  observed_at: z.string(),
  area_km2: z.number(),
  pixels: z.number().int(),
  probability_max: z.number(),
  probability_mean: z.number(),
  components: componentsSchema,
  reason: z.string(),
  why: z.array(z.string()),
  urgency: z.object({
    level: z.enum(URGENCY_LEVELS),
    label: z.string(),
    leaves_1km_h: z.number().nullable(),
    leaves_2km_h: z.number().nullable(),
    beaching: beachingSchema.nullable(),
    beaching_any: z.number().nullable(),
    deadline_h: z.number().nullable(),
  }),
  checks: z.array(z.string()),
  window: z.object({ from: z.string(), to: z.string(), basis: z.string() }).nullable(),
  window_note: z.string().nullable(),
  spot_until: z.string().nullable(),
  nearest_port: z.object({ id: z.string(), name: z.string(), distance_km: z.number() }).nullable(),
  shore_km: z.number().nullable(),
  uav: z.object({ feasible: z.boolean().nullable(), range_km: z.number(), basis: z.string() }),
  method: z.enum(SURVEY_METHODS),
  drift: z
    .object({
      bearing_deg: z.number(),
      km_per_day: z.number(),
      hours: z.number().int(),
      track: z.array(positionSchema),
      radii: z.array(z.object({ hour: z.number(), km: z.number() })),
    })
    .nullable(),
  search_radius: z.object({ base_km: z.number(), km_per_day: z.number() }),
  visit: z.number().int().nullable(),
  eta: z.string().nullable(),
  shift_at_eta_km: z.number().nullable(),
});

const portSchema = z.object({
  id: z.string(),
  name: z.string(),
  name_en: z.string(),
  country: z.string().nullable(),
  sea: z.string().nullable(),
  harbor_size: z.string().nullable(),
  harbor_type: z.string().nullable(),
  position: positionSchema,
  source: z.string(),
  distance_km: z.number().nullable(),
});

const routeSchema = z.object({
  port_id: z.string(),
  order: z.array(z.string()),
  path: z.array(positionSchema),
  legs: z.array(
    z.object({ target_id: z.string(), cumulative_km: z.number(), arrive_h: z.number() }),
  ),
  one_way_km: z.number(),
  distance_km: z.number(),
  duration_h: z.number(),
  speed_kn: z.number(),
  dwell_min: z.number(),
  method: z.string(),
});

const exitWindowSchema = z.object({
  from: z.string(),
  to: z.string(),
  departure: z.string(),
  daylight: z.tuple([z.string(), z.string()]),
  beaching_at: z.string().nullable(),
  scenario_end: z.string().nullable(),
  relaxed: z.enum(["beaching", "scenario_end", "daylight"]).nullable(),
  basis: z.string(),
  past: z.boolean(),
});

const passSchema = z.object({
  id: z.string(),
  platform: z.string(),
  relative_orbit: z.number().int().nullable(),
  acquired_at: z.string(),
  swath: z.tuple([z.number(), z.number()]),
  cloud_cover: z.number().nullable(),
  scenes: z.number().int(),
});

export const surveySchema = z.object({
  analysis_id: z.string(),
  model: z.string(),
  status: z.object({ status: z.enum(SURVEY_STATUSES), label: z.string() }),
  reason: z.string(),
  value_kind: z.string(),
  request: z.object({
    speed_kn: z.number(),
    uav_range_km: z.number(),
    route_targets: z.number().int(),
    dwell_min: z.number(),
    lead_h: z.number(),
  }),
  t0: z.string().nullable(),
  ready_at: z.string().nullable(),
  drift: z.object({
    used: z.boolean(),
    status: z.string().nullable(),
    computed_at: z.string().nullable(),
    hours: z.number().nullable(),
    note: z.string(),
  }),
  zones: z.object({
    total: z.number().int(),
    groups: z.number().int(),
    planned: z.number().int(),
    limit: z.number().int(),
  }),
  weights: z.object({
    confidence: z.number(),
    coverage: z.number(),
    persistence: z.number(),
    drift_risk: z.number(),
    uncertainty: z.number(),
    accessibility: z.number(),
  }),
  scoring: z.record(z.string(), z.string()),
  port: portSchema.nullable(),
  targets: z.array(targetSchema),
  route: routeSchema.nullable(),
  exit_window: exitWindowSchema.nullable(),
  passes: z.array(passSchema),
  passes_note: z.string().nullable(),
  messages: z.array(z.string()),
  computed_at: z.string(),
});

export type SurveyResultStatus = (typeof SURVEY_STATUSES)[number];
export type SurveyResponse = z.infer<typeof surveySchema>;
export type SurveyTargetItem = z.infer<typeof targetSchema>;
export type SurveyPassItem = z.infer<typeof passSchema>;

export type SurveyOptions = {
  speed_kn?: number;
  uav_range_km?: number;
  route_targets?: number;
};

const surveyPath = (analysisId: string) => `/analyses/${encodeURIComponent(analysisId)}/survey`;

export const getSurvey = (analysisId: string, signal?: AbortSignal) =>
  apiRequest(surveyPath(analysisId), surveySchema, { signal });

export const createSurvey = (analysisId: string, options: SurveyOptions = {}) =>
  apiRequest(surveyPath(analysisId), surveySchema, { method: "POST", body: options });
