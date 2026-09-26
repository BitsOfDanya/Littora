import { describe, expect, it } from "vitest";
import { type ModelsResponse, modelsResponseSchema } from "@/lib/api/models";
import {
  confusionOf,
  MODELS_SOURCE,
  PREDICTED_CLASSES,
  reportClasses,
  toModelReport,
} from "./model-report";

const SERVICE = "raunet__marida_mixed__common";

const CI = {
  precision: [0.7386585784642188, 0.9174829931972788],
  recall: [0.9263487998205339, 1.0],
  f1: [0.8309253594128929, 0.9491031773755462],
  iou: [0.7107548262548262, 0.9031364066804407],
};

const metrics = (f1: number) => ({
  precision: 0.8357348703170029,
  recall: 0.9698996655518395,
  f1,
  iou: 0.8146067415730337,
  pr_auc: 0.9763768210137505,
});

const split = (f1: number, pixels = 180209, positives = 299) => ({
  pixels,
  positives,
  true_positives: 290,
  false_positives: 57,
  false_negatives: 9,
  metrics: metrics(f1),
  ci95: CI,
  false_positives_by_class: [
    { label: "ship", pixels: 1163, false_positives: 24 },
    { label: "waves", pixels: 1865, false_positives: 14 },
    { label: "natural_organic_material", pixels: 8, false_positives: 8 },
    { label: "wakes", pixels: 1525, false_positives: 4 },
    { label: "mixed_water", pixels: 61, false_positives: 3 },
    { label: "clouds", pixels: 24862, false_positives: 2 },
    { label: "marine_water", pixels: 18869, false_positives: 1 },
    { label: "foam", pixels: 357, false_positives: 1 },
    { label: "turbid_water", pixels: 31679, false_positives: 0 },
  ],
});

const run = (name: string, valF1: number, overrides: Record<string, unknown> = {}) => ({
  name,
  config_sha256: "2e01de9b8b75098ac4f3fd0981609602eccde54f0a90421ecbbd1681801c0da1",
  method: name.split("__")[0],
  kind: "raunet",
  loss: "bce_dice",
  data: "marida_l2a",
  split: "common",
  members: [],
  weights: [],
  source_run: null,
  threshold: 0.2939169406890869,
  threshold_source: "val_max_f1",
  tta: true,
  inputs: null,
  val: split(valF1, 213080, 1068),
  test: split(0.8421),
  postprocessing: null,
  unlabeled_alarms_per_100km2: null,
  in_service: false,
  ...overrides,
});

const response: ModelsResponse = modelsResponseSchema.parse({
  detector: {
    service: {
      name: SERVICE,
      threshold: 0.15921302139759064,
      min_pixels: 2,
      bands: ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12"],
      patch: 256,
      stride: 192,
      data: "marida_mixed",
      split: "common",
      sea_mask: "море — вода и перистые облака по SCL",
      validation: "порог, TTA и постобработка выбраны на валидации",
      test: metrics(0.8978328173374613),
      test_ci95: CI,
      postprocessed_test: {
        precision: 0.8558558558558559,
        recall: 0.9531772575250836,
        f1: 0.9018987341772151,
        iou: 0.8213256484149856,
      },
    },
    test_set: {
      dataset: "MARIDA",
      data: "marida_mixed",
      split: "common",
      patches: 312,
      scenes: 13,
      pixels: 180209,
      positives: 299,
    },
    runs: [
      run("raunet__marida_l2a__common", 0.9382),
      run(SERVICE, 0.9428571428571428, {
        data: "marida_mixed",
        threshold: 0.15921302139759064,
        in_service: true,
        test: split(0.8978328173374613),
        unlabeled_alarms_per_100km2: 247.40186030381048,
      }),
      run("lgbm_pixel__marida_l2a__common", 0.8742, {
        kind: "lightgbm",
        loss: null,
        tta: null,
        inputs: ["B02", "B08", "B11", "FDI", "NDVI"],
        test: { ...split(0.9048), ci95: null },
      }),
      run("lgbm_pixel__marida", 0.8892, {
        split: "official",
        data: "marida",
        test: split(0.8676, 194863, 381),
      }),
    ],
    checks: {
      domain_shift: [
        run("raunet__marida__on_marida_l2a__common", 0.8427, {
          source_run: "raunet__marida",
          method: "raunet__marida",
          kind: null,
          threshold: 0.706,
          test: split(0.7984344422700588),
        }),
        run("raunet__marida__on_marida__common", 0.9319, {
          source_run: "raunet__marida",
          method: "raunet__marida",
          kind: null,
          data: "marida",
          threshold: 0.706,
          test: split(0.8584337349397592),
        }),
      ],
      leave_region_out: [
        {
          run: "lgbm_pixel__marida_l2a",
          protocol: "регион целиком в тесте",
          regions: [
            {
              region: "honduras",
              positives: 1061,
              threshold: 0.93,
              metrics: { precision: 0.28, recall: 0.77, f1: 0.41, iou: 0.26, pr_auc: 0.4 },
            },
          ],
          pooled: { precision: 0.48, recall: 0.76, f1: 0.59007299270073, iou: 0.42 },
        },
      ],
      black_sea_negatives: {
        run: SERVICE,
        collection: "sentinel-2-l2a",
        definition: "доля пикселей выше замороженного порога",
        pixels: 488727,
        alarm_pixels: 1,
        classes: [
          {
            label: "cloud",
            polygons: 8,
            pixels: 203317,
            area_km2: 20.33,
            alarm_pixels: 0,
            polygons_with_alarm: 0,
          },
          {
            label: "ship",
            polygons: 7,
            pixels: 455,
            area_km2: 0.05,
            alarm_pixels: 1,
            polygons_with_alarm: 1,
          },
        ],
        scenes: [
          { aoi: "sochi_adler", scene_id: "S2C_37TEJ", pixels: 1, detected_pixels: 0, zones: 0 },
          { aoi: "sochi_offshore", scene_id: "S2C_37TEJ", pixels: 1, detected_pixels: 0, zones: 0 },
          {
            aoi: "novorossiysk",
            scene_id: "S2A_37TDK",
            pixels: 1,
            detected_pixels: 101,
            zones: 15,
          },
        ],
      },
      plp: {
        description: "внешняя проверка детектора на мишенях PLP",
        threshold: "замороженный порог detector.json",
        targets: 53,
        usable: 53,
        groups: [
          {
            group: "plastic_or_mixed",
            targets: 37,
            detected: 6,
            rate: 0.16216216216216217,
            ci95: [0.07651103235297099, 0.31136799295455864],
            zone_detected: 4,
          },
          {
            group: "natural_controls",
            targets: 16,
            detected: 1,
            rate: 0.0625,
            ci95: [0.01111905730833121, 0.2832926836802987],
            zone_detected: 1,
          },
        ],
        by_size: [
          { group: "<5 м", targets: 4, detected: 0, rate: 0, ci95: [0, 0.49], zone_detected: 0 },
        ],
        background: {
          windows: 27,
          water_km2: 82.8766,
          zones: 9,
          zones_per_100_km2: 10.86,
          ring_km2: 4.94,
          ring_alarm_pixels: 0,
        },
      },
    },
  },
  concentration: {
    profiles: [
      {
        profile: "S2_visual_GT2",
        target_key: "plastic-visual",
        events: 63,
        survey_days: 26,
        served: {
          model: "median",
          kind: "median",
          gain_over_median: false,
          reason: "значимого выигрыша над медианой нет",
          value: 36.0923965351,
          unit: "items/km2",
          coverage_nominal: 0.8,
          coverage_empirical: 0.819047619047619,
          rule: "кандидат против медианы",
        },
        evaluations: [
          {
            report: "compact",
            role: "shortlist",
            selection: "шорт-лист",
            repetitions: 10,
            baseline_mae: { mean: 34.10508864504031, sd: 0.61 },
            baseline_rmse: { mean: 47.39628725069449, sd: 0.63 },
            nested_mae: { mean: 29.77553470959516, sd: 3.63 },
            nested_rmse: { mean: 41.60116886179549, sd: 4.99 },
            nested_coverage: null,
            difference_mae: {
              mean: -4.329553935445155,
              confidence: 0.95,
              ci: [-11.016386851759403, 2.9599739218711476],
              relative: null,
              relative_ci: null,
            },
            difference_rmse: null,
            gain_over_median: false,
          },
          {
            report: "broad",
            role: "primary",
            selection: "основной результат",
            repetitions: 10,
            baseline_mae: { mean: 34.10508864504031, sd: 0.61 },
            baseline_rmse: { mean: 47.39628725069449, sd: 0.63 },
            nested_mae: { mean: 30.794586979156115, sd: 3.32 },
            nested_rmse: { mean: 43.72160021630371, sd: 5.24 },
            nested_coverage: { mean: 0.75, sd: 0.06 },
            difference_mae: {
              mean: -3.3105016658841997,
              confidence: 0.95,
              ci: [-9.281003572027327, 3.7595611747296664],
              relative: -0.097,
              relative_ci: [-0.226, 0.134],
            },
            difference_rmse: null,
            gain_over_median: false,
          },
        ],
      },
    ],
    satellite_link: {
      detector: SERVICE,
      events: 7,
      correlations: [
        { feature: "fdi_mean", spearman: -0.43, p_value: 0.3373683110858241 },
        { feature: "detected_share", spearman: 0.49, p_value: 0.2614245269466299 },
        { feature: "nir_p99", spearman: null, p_value: null },
      ],
    },
  },
  drift: {
    model: "littora-drift-1",
    status: "scenario",
    label: "сценарий дрейфа",
    reason: "сценарий, а не проверенный прогноз",
    velocity: "u = u_теч + s·u_Стокс + α·U10",
    integration: "RK2 (средняя точка), шаг 900 с",
    windages: [0.005, 0.01, 0.02, 0.03],
    stokes: [true, false],
    particles: 40,
    members: 320,
    diffusivity_m2s: 5,
    horizons_h: [6, 12, 24, 48, 72],
    max_hours: 72,
    max_hindcast_hours: 48,
    forcing: {
      currents: "Open-Meteo Marine · SMOC",
      waves: "Open-Meteo Marine · MFWAM",
      wind: ["ERA5", "Open-Meteo Forecast"],
    },
  },
  sources: ["models/detector/service/detector.json", `reports/metrics/detector/${SERVICE}.json`],
});

describe("model report mapping", () => {
  const report = toModelReport(response);
  const served = report.models.find((model) => model.inUse);

  it("keeps the service run and its test metrics exactly as in the artifacts", () => {
    expect(served?.code).toBe(SERVICE);
    expect(served?.metrics).toEqual({
      f1: 0.8978328173374613,
      iou: 0.8146067415730337,
      precision: 0.8357348703170029,
      recall: 0.9698996655518395,
    });
    expect(served?.metricsCi95?.f1).toEqual(CI.f1);
    expect(served?.threshold).toBe(0.15921302139759064);
    expect(served?.valF1).toBe(0.9428571428571428);
    expect(served?.prAuc).toBe(0.9763768210137505);
    expect(served?.version).toBe("конфиг 2e01de9b");
    expect(report.source).toBe(MODELS_SOURCE);
    expect(report.evaluationSet).toEqual({
      dataset: "MARIDA",
      split: "test",
      patches: 312,
      positivePixels: 299,
      scenes: 13,
    });
  });

  it("compares only runs on the service test set, ordered by validation F1", () => {
    expect(report.models.map((model) => model.code)).toEqual([
      SERVICE,
      "raunet__marida_l2a__common",
      "lgbm_pixel__marida_l2a__common",
    ]);
    expect(report.evidence?.otherTestRuns).toBe(1);
    expect(served?.name).toBe("RA-U-Net, BCE + Dice, MARIDA + L2A");
    expect(report.models[2].family).toBe("LightGBM · пиксельный");
  });

  it("does not invent curves, intervals or inputs the artifacts do not hold", () => {
    for (const model of report.models) expect(model.prCurve).toEqual([]);
    const lgbm = report.models.find((model) => model.code.startsWith("lgbm"));
    expect(lgbm?.metricsCi95).toBeNull();
    expect(lgbm?.inputBands).toEqual(["B02", "B08", "B11", "FDI", "NDVI"]);
    expect(served?.inputBands).toHaveLength(11);
    expect(
      report.models.find((model) => model.code === "raunet__marida_l2a__common")?.inputBands,
    ).toEqual([]);
  });

  it("builds the confusion rows from labelled pixels and detector answers", () => {
    const confusion = served?.confusion;
    expect(confusion?.predicted).toEqual(PREDICTED_CLASSES);
    expect(confusion?.labels).toEqual(report.classes);
    const rows = Object.fromEntries(
      report.classes.map((label, index) => [label, confusion?.counts[index]]),
    );
    expect(rows["Мусор"]).toEqual([290, 9]);
    expect(rows["Судно/след"]).toEqual([28, 1163 + 1525 - 28]);
    expect(rows["Органика"]).toEqual([8, 0]);
    expect(rows["Вода"]).toEqual([4, 18869 + 31679 + 61 - 4]);
    expect(rows["Облака/тени"]).toEqual([2, 24860]);
    expect(rows["Пена"]).toEqual([1, 356]);
    expect(rows["Саргассум"]).toEqual([0, 0]);
    const falsePositives = confusion?.counts.slice(1).reduce((sum, row) => sum + row[0], 0);
    expect(falsePositives).toBe(57);
    expect(served?.falsePositivesByClass?.map((row) => row.label)).toEqual([
      "суда",
      "волны",
      "природная органика",
      "кильватерный след",
      "смешанная вода",
      "облака",
      "морская вода",
      "пена",
    ]);
  });

  it("puts unknown MARIDA classes into a separate row instead of dropping them", () => {
    const runs = response.detector?.runs ?? [];
    const odd = {
      ...runs[0],
      test: {
        ...runs[0].test,
        false_positives_by_class: [{ label: "fog", pixels: 10, false_positives: 3 }],
      },
    };
    const classes = reportClasses([odd]);
    expect(classes.at(-1)).toBe("Прочее");
    expect(confusionOf(odd, classes).counts.at(-1)).toEqual([3, 7]);
  });

  it("maps the service profile and the external checks", () => {
    const evidence = report.evidence;
    expect(evidence?.service?.postprocessed?.f1).toBe(0.9018987341772151);
    expect(evidence?.service?.minPixels).toBe(2);
    expect(evidence?.service?.unlabeledAlarmsPer100Km2).toBe(247.40186030381048);
    const shift = evidence?.domainShift[0];
    expect(shift?.threshold).toBe(0.706);
    expect(shift?.results.map((result) => result.data)).toEqual(["marida", "marida_l2a"]);
    expect(evidence?.regions[0].pooled.f1).toBe(0.59007299270073);
    expect(evidence?.regions[0].regions[0].region).toBe("Гондурас");
    expect(evidence?.negatives).toMatchObject({
      pixels: 488727,
      alarmPixels: 1,
      polygons: 15,
      scenes: 2,
      windowZones: 15,
    });
    expect(evidence?.plp?.plastic).toMatchObject({ detected: 6, targets: 37 });
    expect(evidence?.plp?.natural?.rate).toBe(0.0625);
    expect(evidence?.sources).toEqual(response.sources);
  });

  it("maps concentration and drift without reinterpreting them", () => {
    const profile = report.evidence?.concentration[0];
    expect(profile?.label).toBe("S2 · пластик, визуально");
    expect(profile?.primary?.report).toBe("broad");
    expect(profile?.primary?.difference?.ci).toEqual([-9.281003572027327, 3.7595611747296664]);
    expect(profile?.shortlist?.report).toBe("compact");
    expect(profile?.served).toMatchObject({ model: "median", unit: "шт./км²", gain: false });
    expect(report.evidence?.satelliteLink).toEqual({
      events: 7,
      correlations: 3,
      minPValue: 0.2614245269466299,
      pairs: [],
    });
    expect(report.evidence?.drift?.members).toBe(320);
    expect(report.evidence?.drift?.forcing).toHaveLength(4);
  });

  it("serves an empty model table when only concentration artifacts exist", () => {
    const partial = toModelReport({ ...response, detector: null });
    expect(partial.models).toEqual([]);
    expect(partial.evidence?.service).toBeNull();
    expect(partial.evidence?.concentration).toHaveLength(1);
  });
});
