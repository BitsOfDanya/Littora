import { z } from "zod";
import type { BBox } from "@/domain/geo";
import { resultStatusSchema } from "./analyses";
import { apiRequest, withQuery } from "./client";
import { bboxSchema } from "./geojson";
import { sceneItemSchema } from "./scenes";

const statusSchema = z.object({ status: resultStatusSchema, label: z.string() });

const countsSchema = z.object({
  new: z.number().int(),
  persisting: z.number().int(),
  disappeared: z.number().int(),
  not_observed: z.number().int(),
});

const areasSchema = z.object({
  new: z.number(),
  persisting: z.number(),
  disappeared: z.number(),
  not_observed: z.number(),
});

const passRefSchema = z.object({
  analysis_id: z.string(),
  scene_id: z.string().nullable(),
  acquired_at: z.string().nullable(),
  status: resultStatusSchema,
});

const passAnalysisSchema = z.object({
  id: z.string(),
  computed_at: z.string(),
  window_days: z.number().int(),
  status: statusSchema,
  detection: statusSchema.extend({
    reason: z.string(),
    model: z.string().nullable(),
    threshold: z.number().nullable().optional(),
  }),
  zone_count: z.number().int().nullable(),
  zones_limited: z.boolean(),
  retryable: z.boolean().default(false),
  area_km2: z.number().nullable(),
  probability_max: z.number().nullable(),
  concentration: statusSchema.extend({
    reason: z.string().nullable(),
    value: z.number().nullable(),
    lower: z.number().nullable(),
    upper: z.number().nullable(),
    unit: z.string().nullable(),
  }),
  quality: z
    .object({
      usable: z.boolean(),
      reasons: z.array(z.string()),
      cloud: z.number().nullable().optional(),
      water: z.number().nullable().optional(),
    })
    .nullable(),
  layers: z.array(z.string()),
});

const passChangeSchema = z.object({
  before: passRefSchema,
  counts: countsSchema,
  area_km2: areasSchema,
});

const passSchema = z.object({
  scene: sceneItemSchema,
  analysis: passAnalysisSchema.nullable(),
  change: passChangeSchema.nullable(),
});

export const RUN_STATES = ["queued", "running", "done", "failed"] as const;

const runItemSchema = z.object({
  scene_id: z.string(),
  acquired_at: z.string(),
  state: z.enum(["pending", "running", "done", "cached", "failed"]),
  analysis_id: z.string().nullable(),
  status: statusSchema.nullable(),
  message: z.string().nullable(),
});

export const timelineRunSchema = z.object({
  id: z.string(),
  status: z.enum(RUN_STATES),
  request: z.object({
    bbox: bboxSchema,
    date_from: z.string(),
    date_to: z.string(),
    aoi_id: z.string().nullable(),
    target: z.string().nullable(),
  }),
  current_scene_id: z.string().nullable(),
  created_at: z.string(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  message: z.string().nullable(),
  total: z.number().int(),
  completed: z.number().int(),
  failed: z.number().int(),
  items: z.array(runItemSchema),
});

export const timelineSchema = z.object({
  request: timelineRunSchema.shape.request,
  target: z.object({ key: z.string(), title: z.string() }),
  models: z.object({ detector: z.string().nullable(), concentration: z.string().nullable() }),
  value_kind: z.literal("detections"),
  note: z.string(),
  summary: z.object({
    passes: z.number().int(),
    usable: z.number().int(),
    analysed: z.number().int(),
    comparable: z.number().int(),
  }),
  passes: z.array(passSchema),
  run: timelineRunSchema.nullable(),
  limits: z.object({
    default_passes: z.number().int(),
    max_passes: z.number().int(),
    max_range_days: z.number().int(),
    window_days: z.number().int(),
  }),
});

export const timelineCompareSchema = z.object({
  before: passRefSchema,
  after: passRefSchema,
  value_kind: z.literal("detections"),
  comparable: z.boolean(),
  reason: z.string().nullable(),
  counts: countsSchema.optional(),
  area_km2: areasSchema.optional(),
  after_zones: z.record(z.string(), z.enum(["new", "persisting", "not_observed"])).optional(),
  before_zones: z
    .record(z.string(), z.enum(["persisting", "disappeared", "not_observed"]))
    .optional(),
  masks_checked: z.boolean().optional(),
  tolerance_m: z.number().optional(),
  method: z.string().optional(),
});

export type Timeline = z.infer<typeof timelineSchema>;
export type TimelinePass = z.infer<typeof passSchema>;
export type TimelinePassAnalysis = z.infer<typeof passAnalysisSchema>;
export type TimelineRun = z.infer<typeof timelineRunSchema>;
export type TimelineCompare = z.infer<typeof timelineCompareSchema>;
export type ZoneChange = z.infer<typeof countsSchema>;

export type TimelineQuery = {
  aoiId: string;
  bbox: BBox;
  dateFrom: string;
  dateTo: string;
  target?: string | null;
};

export type TimelineRunCreate = {
  bbox: BBox;
  date_from: string;
  date_to: string;
  aoi_id?: string | null;
  aoi_name?: string | null;
  target?: string | null;
  max_passes?: number;
  scene_ids?: string[] | null;
};

export const getTimeline = (query: TimelineQuery, signal?: AbortSignal) =>
  apiRequest(
    withQuery("/timeline", {
      bbox: query.bbox.join(","),
      date_from: query.dateFrom,
      date_to: query.dateTo,
      aoi_id: query.aoiId,
      target: query.target,
    }),
    timelineSchema,
    { signal },
  );

export const createTimelineRun = (body: TimelineRunCreate) =>
  apiRequest("/timeline/runs", timelineRunSchema, { method: "POST", body });

export const getTimelineCompare = (before: string, after: string, signal?: AbortSignal) =>
  apiRequest(withQuery("/timeline/compare", { before, after }), timelineCompareSchema, {
    signal,
  });
