import { z } from "zod";

export const positionSchema = z.tuple([z.number(), z.number()]);

export const bboxSchema = z.tuple([z.number(), z.number(), z.number(), z.number()]);

export const pointSchema = z.object({ type: z.literal("Point"), coordinates: positionSchema });

export const lineStringSchema = z.object({
  type: z.literal("LineString"),
  coordinates: z.array(positionSchema),
});

export const polygonSchema = z.object({
  type: z.literal("Polygon"),
  coordinates: z.array(z.array(positionSchema)),
});

export const multiPolygonSchema = z.object({
  type: z.literal("MultiPolygon"),
  coordinates: z.array(z.array(z.array(positionSchema))),
});

export const areaGeometrySchema = z.discriminatedUnion("type", [polygonSchema, multiPolygonSchema]);

export const geometrySchema = z.discriminatedUnion("type", [
  pointSchema,
  lineStringSchema,
  polygonSchema,
  multiPolygonSchema,
]);

export type AreaGeometry = z.infer<typeof areaGeometrySchema>;
export type AnyGeometry = z.infer<typeof geometrySchema>;
