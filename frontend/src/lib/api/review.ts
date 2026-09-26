import { z } from "zod";
import { apiRequest, apiUrl, withQuery } from "./client";
import { geometrySchema, positionSchema } from "./geojson";

export const REVIEW_LABELS = [
  "likely_debris",
  "ship",
  "structure",
  "wake",
  "foam",
  "slick",
  "plume",
  "land_edge",
  "cloud_edge",
  "water",
  "unknown",
] as const;

export const REVIEW_SOURCES = ["ui", "audit"] as const;

export const reviewLabelSchema = z.enum(REVIEW_LABELS);
export const reviewSourceSchema = z.enum(REVIEW_SOURCES);

export const reviewRecordSchema = z.object({
  id: z.string(),
  source: reviewSourceSchema,
  source_title: z.string(),
  created_at: z.string().nullable(),
  analysis_id: z.string().nullable(),
  zone_id: z.string(),
  audit_zone_id: z.string().optional(),
  reviewer: z.string().nullable(),
  label: reviewLabelSchema,
  label_title: z.string(),
  confidence: z.number().int().min(1).max(3),
  comment: z.string().nullable(),
  aoi_id: z.string().nullable(),
  aoi_name: z.string().nullable(),
  scene_id: z.string().nullable(),
  date: z.string().nullable(),
  model_fingerprint: z.string().nullable(),
  probability_max: z.number().nullable(),
  centroid: positionSchema.nullable(),
  geometry: geometrySchema.nullable(),
});

const labelShareSchema = z.object({
  label: reviewLabelSchema,
  title: z.string(),
  zones: z.number().int(),
  share: z.number().nullable(),
});

export const reviewStatsSchema = z.object({
  reviews: z.number().int(),
  zones: z.number().int(),
  labels: z.array(labelShareSchema),
  disputed: z.number().int(),
  precision: z.object({
    debris: z.number().int(),
    zones: z.number().int(),
    value: z.number().nullable(),
    interval: z.tuple([z.number(), z.number()]).nullable(),
    decided: z.number().int(),
    decided_value: z.number().nullable(),
  }),
  agreement: z.object({
    zones: z.number().int(),
    agreed: z.number().int(),
    value: z.number().nullable(),
  }),
});

export const zoneReviewsSchema = z.object({
  zone_id: z.string(),
  consensus: reviewLabelSchema.nullable(),
  reviews: z.array(reviewRecordSchema),
  history: z.number().int(),
  audit: z.array(reviewRecordSchema),
});

export const analysisReviewsSchema = z.object({
  analysis_id: z.string(),
  zones_total: z.number().int(),
  zones: z.array(zoneReviewsSchema),
  items: z.array(reviewRecordSchema),
  summary: reviewStatsSchema.extend({ zones_total: z.number().int() }),
  audit: reviewStatsSchema.extend({
    source: reviewSourceSchema,
    title: z.string(),
    available: z.boolean(),
    matched: z.number().int(),
  }),
});

const sourceSummarySchema = reviewStatsSchema.extend({
  source: reviewSourceSchema,
  title: z.string(),
  available: z.boolean(),
  by_aoi: z.array(
    reviewStatsSchema.extend({ aoi_id: z.string().nullable(), aoi_name: z.string().nullable() }),
  ),
});

export const reviewListSchema = z.object({
  items: z.array(reviewRecordSchema),
  summary: z.object({ sources: z.array(sourceSummarySchema) }),
});

export type ReviewLabel = z.infer<typeof reviewLabelSchema>;
export type ReviewSource = z.infer<typeof reviewSourceSchema>;
export type ReviewRecord = z.infer<typeof reviewRecordSchema>;
export type ReviewStats = z.infer<typeof reviewStatsSchema>;
export type ZoneReviews = z.infer<typeof zoneReviewsSchema>;
export type AnalysisReviews = z.infer<typeof analysisReviewsSchema>;
export type ReviewList = z.infer<typeof reviewListSchema>;
export type ReviewSourceSummary = z.infer<typeof sourceSummarySchema>;

export type ReviewInput = {
  label: ReviewLabel;
  confidence: 1 | 2 | 3;
  comment: string | null;
  reviewer: string | null;
};

export type ReviewFilters = {
  source?: ReviewSource;
  analysis_id?: string;
  aoi_id?: string;
  scene_id?: string;
  label?: ReviewLabel;
  reviewer?: string;
  history?: boolean;
};

export type ReviewExportFormat = "geojson" | "csv";

function filterParams(filters: ReviewFilters) {
  return { ...filters, history: filters.history ? "true" : undefined };
}

export function getAnalysisReviews(analysisId: string, signal?: AbortSignal) {
  return apiRequest(`/analyses/${encodeURIComponent(analysisId)}/reviews`, analysisReviewsSchema, {
    signal,
  });
}

export function createReview(analysisId: string, zoneId: string, input: ReviewInput) {
  return apiRequest(
    `/analyses/${encodeURIComponent(analysisId)}/zones/${encodeURIComponent(zoneId)}/review`,
    reviewRecordSchema,
    { method: "POST", body: input },
  );
}

export function getReviews(filters: ReviewFilters = {}, signal?: AbortSignal) {
  return apiRequest(withQuery("/reviews", filterParams(filters)), reviewListSchema, { signal });
}

export function reviewExportUrl(format: ReviewExportFormat, filters: ReviewFilters = {}): string {
  return apiUrl(withQuery(`/reviews/export.${format}`, filterParams(filters)));
}
