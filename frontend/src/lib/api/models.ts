import { z } from "zod";
import { apiRequest } from "./client";

const intervalSchema = z.tuple([z.number(), z.number()]);

const metricsSchema = z.object({
  precision: z.number(),
  recall: z.number(),
  f1: z.number(),
  iou: z.number(),
  pr_auc: z.number().nullable().optional(),
});

const intervalsSchema = z.object({
  precision: intervalSchema,
  recall: intervalSchema,
  f1: intervalSchema,
  iou: intervalSchema,
});

const splitSchema = z.object({
  pixels: z.number().int(),
  positives: z.number().int(),
  true_positives: z.number().int().nullable(),
  false_positives: z.number().int().nullable(),
  false_negatives: z.number().int().nullable(),
  metrics: metricsSchema,
  ci95: intervalsSchema.nullable(),
  false_positives_by_class: z.array(
    z.object({
      label: z.string(),
      pixels: z.number().int(),
      false_positives: z.number().int(),
    }),
  ),
});

export const detectorRunSchema = z.object({
  name: z.string(),
  config_sha256: z.string().nullable(),
  method: z.string(),
  kind: z.string().nullable(),
  loss: z.string().nullable(),
  data: z.string(),
  split: z.string().nullable(),
  members: z.array(z.string()),
  weights: z.array(z.number()),
  source_run: z.string().nullable(),
  threshold: z.number(),
  threshold_source: z.string().nullable(),
  tta: z.boolean().nullable(),
  inputs: z.array(z.string()).nullable(),
  val: splitSchema.nullable(),
  test: splitSchema,
  postprocessing: z
    .object({
      threshold: z.number(),
      min_pixels: z.number().int(),
      scene_classes: z.boolean(),
      ship_veto: z.boolean(),
      test: metricsSchema.nullable(),
    })
    .nullable(),
  unlabeled_alarms_per_100km2: z.number().nullable(),
  in_service: z.boolean(),
});

const detectorServiceSchema = z.object({
  name: z.string(),
  threshold: z.number(),
  min_pixels: z.number().int(),
  bands: z.array(z.string()),
  patch: z.number().int().nullable(),
  stride: z.number().int().nullable(),
  data: z.string().nullable(),
  split: z.string().nullable(),
  sea_mask: z.string().nullable(),
  validation: z.string().nullable(),
  test: metricsSchema.nullable(),
  test_ci95: intervalsSchema.nullable(),
  postprocessed_test: metricsSchema.nullable(),
  service_test: metricsSchema.nullable().optional(),
  service_mode: z.string().nullable().optional(),
  calibration: z.string().nullable().optional(),
});

const detectionRateSchema = z.object({
  group: z.string(),
  targets: z.number().int(),
  detected: z.number().int(),
  rate: z.number(),
  ci95: intervalSchema.nullable(),
  zone_detected: z.number().int().nullable(),
});

const detectorChecksSchema = z.object({
  domain_shift: z.array(detectorRunSchema),
  leave_region_out: z.array(
    z.object({
      run: z.string(),
      protocol: z.string().nullable(),
      regions: z.array(
        z.object({
          region: z.string(),
          positives: z.number().int(),
          threshold: z.number().nullable(),
          metrics: metricsSchema,
        }),
      ),
      pooled: metricsSchema,
    }),
  ),
  black_sea_negatives: z
    .object({
      run: z.string(),
      collection: z.string().nullable(),
      definition: z.string().nullable(),
      pixels: z.number().int(),
      alarm_pixels: z.number().int(),
      classes: z.array(
        z.object({
          label: z.string(),
          polygons: z.number().int(),
          pixels: z.number().int(),
          area_km2: z.number(),
          alarm_pixels: z.number().int(),
          polygons_with_alarm: z.number().int(),
        }),
      ),
      scenes: z.array(
        z.object({
          aoi: z.string(),
          scene_id: z.string(),
          pixels: z.number().int(),
          detected_pixels: z.number().int(),
          zones: z.number().int(),
        }),
      ),
    })
    .nullable(),
  plp: z
    .object({
      description: z.string().nullable(),
      threshold: z.string().nullable(),
      targets: z.number().int(),
      usable: z.number().int(),
      groups: z.array(detectionRateSchema),
      by_size: z.array(detectionRateSchema),
      background: z
        .object({
          windows: z.number().int(),
          water_km2: z.number(),
          zones: z.number().int(),
          zones_per_100_km2: z.number(),
          ring_km2: z.number(),
          ring_alarm_pixels: z.number().int(),
        })
        .nullable(),
    })
    .nullable(),
  zone_flags: z
    .array(
      z.object({
        kind: z.string(),
        title: z.string(),
        rule: z.string(),
        in_service: z.boolean(),
        shares: z.array(
          z.object({
            part: z.string(),
            group: z.string(),
            objects: z.number().int(),
            flagged: z.number().int(),
            share: z.number().nullable(),
          }),
        ),
        discrimination: z
          .array(
            z.object({
              part: z.string(),
              measure: z.string(),
              value: z.number().nullable(),
              ci95: intervalSchema.nullable(),
            }),
          )
          .default([]),
      }),
    )
    .default([]),
  collection: z
    .object({
      alignment: z.string(),
      rule: z.string(),
      chosen: z.string(),
      rows: z.array(
        z.object({
          run: z.string(),
          in_service: z.boolean(),
          part: z.string(),
          mode: z.string(),
          patches: z.number().int(),
          scenes: z.number().int(),
          c1_f1: z.number(),
          c1_ci95: intervalSchema.nullable(),
          l2a_f1: z.number(),
          l2a_ci95: intervalSchema.nullable(),
          difference: z.number(),
          difference_ci95: intervalSchema.nullable(),
        }),
      ),
    })
    .nullable()
    .default(null),
});

const meanSdSchema = z.object({ mean: z.number(), sd: z.number().nullable() });

const differenceSchema = z.object({
  mean: z.number(),
  confidence: z.number(),
  ci: intervalSchema,
  relative: z.number().nullable(),
  relative_ci: intervalSchema.nullable(),
});

const concentrationSchema = z.object({
  profiles: z.array(
    z.object({
      profile: z.string(),
      target_key: z.string().nullable(),
      events: z.number().int().nullable(),
      survey_days: z.number().int().nullable(),
      served: z
        .object({
          model: z.string(),
          kind: z.string().nullable(),
          gain_over_median: z.boolean(),
          reason: z.string().nullable(),
          value: z.number().nullable(),
          unit: z.string().nullable(),
          coverage_nominal: z.number().nullable(),
          coverage_empirical: z.number().nullable(),
          rule: z.string().nullable(),
        })
        .nullable(),
      evaluations: z.array(
        z.object({
          report: z.string(),
          role: z.string().nullable(),
          selection: z.string().nullable(),
          repetitions: z.number().int().nullable(),
          baseline_mae: meanSdSchema,
          baseline_rmse: meanSdSchema,
          nested_mae: meanSdSchema,
          nested_rmse: meanSdSchema,
          nested_coverage: meanSdSchema.nullable(),
          difference_mae: differenceSchema.nullable(),
          difference_rmse: differenceSchema.nullable(),
          gain_over_median: z.boolean(),
        }),
      ),
    }),
  ),
  satellite_link: z
    .object({
      detector: z.string().nullable(),
      events: z.number().int(),
      correlations: z.array(
        z.object({
          feature: z.string(),
          spearman: z.number().nullable(),
          p_value: z.number().nullable(),
        }),
      ),
      pairs: z
        .array(
          z.object({
            event_id: z.string(),
            scene_id: z.string(),
            concentration: z.number().nullable(),
            water_pixels: z.number().int().nullable(),
            detected_share: z.number().nullable(),
            probability_p99: z.number().nullable(),
            fdi_p99: z.number().nullable(),
          }),
        )
        .default([]),
    })
    .nullable(),
});

const driftMethodSchema = z.object({
  model: z.string(),
  status: z.string(),
  label: z.string(),
  reason: z.string(),
  velocity: z.string(),
  integration: z.string(),
  windages: z.array(z.number()),
  stokes: z.array(z.boolean()),
  particles: z.number().int(),
  members: z.number().int(),
  diffusivity_m2s: z.number(),
  horizons_h: z.array(z.number().int()),
  max_hours: z.number().int(),
  max_hindcast_hours: z.number().int(),
  forcing: z.object({
    currents: z.string(),
    waves: z.string(),
    wind: z.array(z.string()),
  }),
  envelope_spread: z.string().nullable().optional(),
  envelope_domain_margin_km: z.number().nullable().optional(),
  validation: z
    .object({
      errors: z.array(
        z.object({
          key: z.string(),
          label: z.string(),
          horizons: z.array(
            z.object({
              horizon_h: z.number().int(),
              windows: z.number().int(),
              service_km: z.number(),
              stationary_km: z.number(),
              persistence_km: z.number(),
            }),
          ),
        }),
      ),
      calibration: z
        .object({
          nominal: z.number(),
          sets: z.array(
            z.object({
              key: z.string(),
              label: z.string(),
              windows: z.number().int(),
              horizons: z.array(
                z.object({ horizon_h: z.number().int(), before: z.number(), after: z.number() }),
              ),
            }),
          ),
        })
        .nullable(),
    })
    .nullable()
    .optional(),
});

export const modelsResponseSchema = z.object({
  detector: z
    .object({
      service: detectorServiceSchema.nullable(),
      test_set: z
        .object({
          dataset: z.string(),
          data: z.string(),
          split: z.string(),
          patches: z.number().int().nullable(),
          scenes: z.number().int().nullable(),
          pixels: z.number().int(),
          positives: z.number().int(),
        })
        .nullable(),
      runs: z.array(detectorRunSchema),
      checks: detectorChecksSchema,
    })
    .nullable(),
  concentration: concentrationSchema.nullable(),
  drift: driftMethodSchema.nullable(),
  sources: z.array(z.string()),
});

export type DetectorRunItem = z.infer<typeof detectorRunSchema>;
export type ModelsResponse = z.infer<typeof modelsResponseSchema>;
export type DetectorItem = NonNullable<ModelsResponse["detector"]>;
export type DetectorChecksItem = DetectorItem["checks"];
export type ConcentrationItem = NonNullable<ModelsResponse["concentration"]>;
export type DriftMethodItem = NonNullable<ModelsResponse["drift"]>;

export const getModels = (signal?: AbortSignal) =>
  apiRequest("/models", modelsResponseSchema, { signal });
