import { z } from "zod";
import type { BBox } from "@/domain/geo";
import { apiRequest, withQuery } from "./client";
import { lineStringSchema, pointSchema } from "./geojson";

export const caseTargetSchema = z.object({
  key: z.string(),
  primary: z.boolean(),
  title: z.string(),
  material: z.string(),
  size_class: z.string(),
  unit: z.string(),
  profiles: z.array(z.string()),
  target_scope: z.array(z.string()),
  rationale: z.string(),
  records: z.number().int(),
  events: z.number().int(),
});

export const caseTargetsSchema = z.object({
  primary: z.string(),
  targets: z.array(caseTargetSchema),
});

export const observationPropertiesSchema = z.object({
  sample_id: z.string(),
  event_id: z.string(),
  source_id: z.string(),
  source_short: z.string(),
  source_doi: z.string(),
  source_license: z.string(),
  region: z.string(),
  sea_area: z.string(),
  sampling_method: z.string(),
  platform: z.string(),
  measurement_profile: z.string(),
  target_scope: z.string(),
  material: z.string(),
  size_class: z.string(),
  date: z.string(),
  time_start: z.string().nullable(),
  time_end: z.string().nullable(),
  position_role: z.string(),
  value_kind: z.literal("measurement"),
  concentration: z.number().nullable(),
  recomputed: z.number().nullable(),
  unit: z.string(),
  items: z.number().nullable(),
  area_km2: z.number().nullable(),
  check: z.string(),
  check_label: z.string(),
  target_key: z.string().nullable(),
  decision: z.enum(["accepted", "rejected"]),
  reason_code: z.string(),
  reason: z.string(),
  quality_flags: z.array(z.string()),
  pair_decision: z.string().nullable(),
  pair_reason: z.string().nullable(),
  pair_scene_id: z.string().nullable(),
  delta_days: z.number().int().nullable().optional(),
  synchronous: z.boolean().optional(),
});

export const observationSchema = z.object({
  type: z.literal("Feature"),
  id: z.string(),
  geometry: z.discriminatedUnion("type", [pointSchema, lineStringSchema]),
  properties: observationPropertiesSchema,
});

export const observationCollectionSchema = z.object({
  type: z.literal("FeatureCollection"),
  features: z.array(observationSchema),
});

export type CaseTarget = z.infer<typeof caseTargetSchema>;
export type CaseTargets = z.infer<typeof caseTargetsSchema>;
export type FieldObservation = z.infer<typeof observationSchema>;
export type ObservationProperties = z.infer<typeof observationPropertiesSchema>;

export type ObservationQuery = {
  bbox?: BBox;
  target?: string;
  decision?: "accepted" | "rejected";
  dateFrom?: string;
  dateTo?: string;
};

export const getCaseTargets = (signal?: AbortSignal) =>
  apiRequest("/case/targets", caseTargetsSchema, { signal });

export const getObservations = (query: ObservationQuery, signal?: AbortSignal) =>
  apiRequest(
    withQuery("/observations", {
      bbox: query.bbox?.join(","),
      target: query.target,
      decision: query.decision,
      date_from: query.dateFrom,
      date_to: query.dateTo,
    }),
    observationCollectionSchema,
    { signal },
  ).then((collection) => collection.features);
