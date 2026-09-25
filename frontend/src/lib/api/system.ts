import { z } from "zod";
import { apiRequest } from "./client";

export const capabilityKeySchema = z.enum([
  "scene_catalog",
  "field_observations",
  "pair_registry",
  "quality_masks",
  "analysis_requests",
  "export",
  "debris_detection",
  "segmentation",
  "coverage_estimation",
  "spectral_composites",
  "concentration_model",
  "change_tracking",
  "drift_forecast",
  "survey_planning",
  "model_evaluation",
]);

export const healthSchema = z.object({
  status: z.literal("ok"),
  service: z.string(),
  version: z.string(),
  environment: z.string(),
  timestamp: z.iso.datetime({ offset: true }),
});

export const metaSchema = z.object({
  service: z.string(),
  version: z.string(),
  api_version: z.string(),
  environment: z.string(),
  capabilities: z.array(
    z.object({
      key: capabilityKeySchema,
      status: z.enum(["available", "planned"]),
    }),
  ),
});

export type CapabilityKey = z.infer<typeof capabilityKeySchema>;
export type Health = z.infer<typeof healthSchema>;
export type Meta = z.infer<typeof metaSchema>;

export const getHealth = (signal?: AbortSignal) => apiRequest("/health", healthSchema, { signal });
export const getMeta = (signal?: AbortSignal) => apiRequest("/meta", metaSchema, { signal });
