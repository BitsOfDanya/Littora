import { z } from "zod";
import type { BBox } from "@/domain/geo";
import type { SceneSummary } from "@/domain/scene";
import { apiRequest, withQuery } from "./client";
import { areaGeometrySchema, bboxSchema } from "./geojson";

export const sceneItemSchema = z.object({
  id: z.string(),
  aoi_id: z.string().nullable(),
  collection: z.string(),
  platform: z.enum(["S2A", "S2B", "S2C"]),
  processing_level: z.literal("L2A"),
  acquired_at: z.string(),
  mgrs_tile: z.string(),
  relative_orbit: z.number().int().nullable(),
  footprint: bboxSchema,
  geometry: areaGeometrySchema.nullable(),
  area_coverage: z.number(),
  cloud_cover: z.number(),
  valid_water_fraction: z.number(),
  water_fraction: z.number().nullable(),
  sun_glint_risk: z.enum(["low", "moderate", "high"]),
  sun_zenith_deg: z.number().nullable(),
  usability: z.enum(["usable", "partial", "unusable"]),
});

export const sceneListSchema = z.object({ items: z.array(sceneItemSchema) });

export type SceneItem = z.infer<typeof sceneItemSchema>;

export type SceneQuery = { aoiId: string; bbox: BBox; dateFrom: string; dateTo: string };

export function toSceneSummary(item: SceneItem, aoiId: string): SceneSummary {
  return {
    id: item.id,
    aoiId,
    platform: item.platform,
    processingLevel: item.processing_level,
    acquiredAt: item.acquired_at,
    mgrsTile: item.mgrs_tile,
    relativeOrbit: item.relative_orbit,
    footprint: item.footprint,
    outline: item.geometry,
    areaCoverage: item.area_coverage,
    cloudCover: item.cloud_cover,
    validWaterFraction: item.valid_water_fraction,
    sunGlintRisk: item.sun_glint_risk,
    sunZenithDeg: item.sun_zenith_deg,
    usability: item.usability,
  };
}

export const getScenes = (query: SceneQuery, signal?: AbortSignal) =>
  apiRequest(
    withQuery("/scenes", {
      bbox: query.bbox.join(","),
      date_from: query.dateFrom,
      date_to: query.dateTo,
      aoi_id: query.aoiId,
    }),
    sceneListSchema,
    { signal },
  ).then((list) => list.items.map((item) => toSceneSummary(item, query.aoiId)));
