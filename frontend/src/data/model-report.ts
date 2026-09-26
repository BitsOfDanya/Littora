import type { ClassificationMetrics, ConfusionMatrix, ModelTask } from "@/domain/model";
import type {
  ConcentrationItem,
  DetectorChecksItem,
  DetectorItem,
  DetectorRunItem,
  DriftMethodItem,
  ModelsResponse,
} from "@/lib/api/models";
import type {
  ConcentrationEstimate,
  ConcentrationProfile,
  DetectionRate,
  DomainShiftCheck,
  DriftMethodSummary,
  EvaluationSet,
  ModelEvaluation,
  ModelEvidence,
  ModelReport,
  NegativesCheck,
  PlpCheck,
  RegionCheck,
  SatelliteLinkCheck,
  ServiceProfile,
} from "./models";

export const MODELS_SOURCE = "GET /api/v1/models";

export const TARGET_CLASS = "Мусор";

export const PREDICTED_CLASSES = ["Мусор", "Не мусор"] as const;

const OTHER_GROUP = "Прочее";

const LABEL_GROUPS: readonly { label: string; classes: readonly string[] }[] = [
  { label: TARGET_CLASS, classes: ["marine_debris"] },
  { label: "Саргассум", classes: ["dense_sargassum", "sparse_sargassum"] },
  { label: "Органика", classes: ["natural_organic_material"] },
  { label: "Пена", classes: ["foam"] },
  { label: "Судно/след", classes: ["ship", "wakes"] },
  { label: "Волны", classes: ["waves"] },
  { label: "Облака/тени", classes: ["clouds", "cloud_shadows"] },
  {
    label: "Вода",
    classes: [
      "marine_water",
      "sediment_laden_water",
      "turbid_water",
      "shallow_water",
      "mixed_water",
    ],
  },
];

const CLASS_LABELS: Record<string, string> = {
  marine_debris: "мусор",
  dense_sargassum: "плотный саргассум",
  sparse_sargassum: "редкий саргассум",
  natural_organic_material: "природная органика",
  foam: "пена",
  ship: "суда",
  wakes: "кильватерный след",
  waves: "волны",
  clouds: "облака",
  cloud_shadows: "тени облаков",
  marine_water: "морская вода",
  sediment_laden_water: "вода со взвесью",
  turbid_water: "мутная вода",
  shallow_water: "мелководье",
  mixed_water: "смешанная вода",
};

const METHOD_NAMES: Record<string, string> = {
  raunet: "RA-U-Net, BCE + Dice",
  raunet_hard: "RA-U-Net, веса трудных классов",
  raunet_aux: "RA-U-Net + многоклассовая голова",
  raunet_focal_dice: "RA-U-Net, Focal + Dice",
  raunet_focal_tversky: "RA-U-Net, Focal + Tversky",
  unetpp_resnet34: "U-Net++ (ResNet34)",
  rf_pixel: "Random Forest",
  lgbm_pixel: "LightGBM: каналы, индексы, окрестность",
  lgbm_bands_indices: "LightGBM: каналы и индексы",
  lgbm_bands: "LightGBM: только каналы",
  lgbm_rgb: "LightGBM: только RGB",
  fdi_rule: "Правило FDI + NDVI",
  fdi_threshold: "FDI, порог",
};

const KIND_FAMILIES: Record<string, string> = {
  raunet: "Residual Attention U-Net",
  unetplusplus: "U-Net++ · энкодер ResNet-34",
  lightgbm: "LightGBM · пиксельный",
  random_forest: "Random Forest · пиксельный",
  fdi: "Индекс FDI · порог",
  fdi_rule: "Правило по FDI, NDVI и синему",
};

const SEGMENTATION_KINDS = new Set(["raunet", "unetplusplus"]);

export const DATA_LABELS: Record<string, string> = {
  marida: "MARIDA (ACOLITE)",
  marida_l2a: "MARIDA на L2A",
  marida_mixed: "MARIDA + L2A",
};

const DEFAULT_DATA = "marida_l2a";

const REGION_LABELS: Record<string, string> = {
  east_asia: "Восточная Азия",
  hispaniola: "Эспаньола",
  honduras: "Гондурас",
  indonesia: "Индонезия",
  scotland: "Шотландия",
  south_africa: "ЮАР",
  south_china_sea: "Южно-Китайское море",
};

const NEGATIVE_LABELS: Record<string, string> = {
  aquaculture: "садки",
  cloud: "облака",
  river_plume: "речной шлейф",
  ship: "суда",
  slick: "пятна на воде",
  turbid_front: "фронт мутности",
  water: "вода",
};

const PROFILE_LABELS: Record<string, string> = {
  S1_trawl_5_to_50: "S1 · пластик 5–50 см, трал",
  S2_visual_GT2: "S2 · пластик, визуально",
  S3_visual_GT2: "S3 · мусор, визуально",
  S4_visual_GT2_5: "S4 · мусор, визуально",
};

const UNIT_LABELS: Record<string, string> = { "items/km2": "шт./км²" };

const PRIMARY_ROLE = "primary";
const SHORTLIST_ROLE = "shortlist";

const methodName = (run: DetectorRunItem): string => {
  if (run.members.length) return `Ансамбль из ${run.members.length} моделей`;
  const base = METHOD_NAMES[run.method] ?? run.method;
  return run.data === DEFAULT_DATA ? base : `${base}, ${DATA_LABELS[run.data] ?? run.data}`;
};

const formatWeight = (value: number) => value.toFixed(1).replace(".", ",");

const familyOf = (run: DetectorRunItem): string => {
  if (run.members.length)
    return run.weights.length
      ? `Среднее · веса ${run.weights.map(formatWeight).join("/")}`
      : "Среднее вероятностей";
  return (run.kind && KIND_FAMILIES[run.kind]) ?? run.kind ?? run.method;
};

const taskOf = (run: DetectorRunItem): ModelTask =>
  run.members.length || (run.kind !== null && SEGMENTATION_KINDS.has(run.kind))
    ? "segmentation"
    : "pixel_classification";

const pickMetrics = (metrics: ClassificationMetrics): ClassificationMetrics => ({
  f1: metrics.f1,
  iou: metrics.iou,
  precision: metrics.precision,
  recall: metrics.recall,
});

const classLabel = (label: string) => CLASS_LABELS[label] ?? label.replaceAll("_", " ");

export function reportClasses(runs: readonly DetectorRunItem[]): readonly string[] {
  const known = new Set(LABEL_GROUPS.flatMap((group) => group.classes));
  const unknown = runs.some((run) =>
    run.test.false_positives_by_class.some((row) => !known.has(row.label)),
  );
  const labels = LABEL_GROUPS.map((group) => group.label);
  return unknown ? [...labels, OTHER_GROUP] : labels;
}

export function confusionOf(run: DetectorRunItem, classes: readonly string[]): ConfusionMatrix {
  const counts = classes.map(() => [0, 0]);
  const rowOf = (label: string) => {
    const group = LABEL_GROUPS.find((item) => item.classes.includes(label))?.label ?? OTHER_GROUP;
    return classes.indexOf(group);
  };
  const test = run.test;
  const found = test.true_positives ?? Math.round(test.metrics.recall * test.positives);
  counts[rowOf("marine_debris")] = [found, test.positives - found];
  for (const row of test.false_positives_by_class) {
    const index = rowOf(row.label);
    if (index <= 0) continue;
    counts[index][0] += row.false_positives;
    counts[index][1] += row.pixels - row.false_positives;
  }
  return { labels: classes, predicted: PREDICTED_CLASSES, counts };
}

function toEvaluation(
  run: DetectorRunItem,
  classes: readonly string[],
  service: DetectorItem["service"],
  evaluatedOn: string,
): ModelEvaluation {
  const errors = run.test.false_positives_by_class
    .filter((row) => row.false_positives > 0)
    .sort((a, b) => b.false_positives - a.false_positives)
    .map((row) => ({
      label: classLabel(row.label),
      pixels: row.pixels,
      falsePositives: row.false_positives,
    }));
  return {
    id: run.name,
    code: run.name,
    name: methodName(run),
    family: familyOf(run),
    task: taskOf(run),
    version: run.config_sha256 ? `конфиг ${run.config_sha256.slice(0, 8)}` : "",
    inUse: run.in_service,
    inputBands: run.inputs ?? (run.in_service && service ? service.bands : []),
    trainingData: [run.data],
    threshold: run.threshold,
    metrics: pickMetrics(run.test.metrics),
    metricsCi95: run.test.ci95,
    evaluatedOn,
    prCurve: [],
    confusion: confusionOf(run, classes),
    knownFailureModes: errors.map((row) => row.label),
    valF1: run.val?.metrics.f1 ?? null,
    prAuc: run.test.metrics.pr_auc ?? null,
    falsePositivesByClass: errors,
  };
}

const byValidation = (a: DetectorRunItem, b: DetectorRunItem) =>
  (b.val?.metrics.f1 ?? -1) - (a.val?.metrics.f1 ?? -1) || a.name.localeCompare(b.name);

function comparableRuns(detector: DetectorItem): readonly DetectorRunItem[] {
  const testSet = detector.test_set;
  if (!testSet) return detector.runs;
  return detector.runs.filter(
    (run) =>
      run.split === testSet.split &&
      run.test.pixels === testSet.pixels &&
      run.test.positives === testSet.positives,
  );
}

function evaluationSetOf(detector: DetectorItem, served: DetectorRunItem | null): EvaluationSet {
  const testSet = detector.test_set;
  if (testSet)
    return {
      dataset: testSet.dataset,
      split: "test",
      patches: testSet.patches,
      positivePixels: testSet.positives,
      scenes: testSet.scenes,
    };
  return {
    dataset: "MARIDA",
    split: "test",
    patches: null,
    positivePixels: served?.test.positives ?? 0,
    scenes: null,
  };
}

function serviceProfile(
  detector: DetectorItem,
  served: DetectorRunItem | null,
): ServiceProfile | null {
  const service = detector.service;
  if (!service && !served) return null;
  const postprocessed = service?.postprocessed_test ?? served?.postprocessing?.test ?? null;
  return {
    code: service?.name ?? served?.name ?? "",
    threshold: service?.threshold ?? served?.threshold ?? 0,
    thresholdSource: served?.threshold_source ?? null,
    minPixels: service?.min_pixels ?? served?.postprocessing?.min_pixels ?? 1,
    bands: service?.bands ?? [],
    seaMask: service?.sea_mask ?? null,
    validation: service?.validation ?? null,
    tta: served?.tta ?? null,
    prAuc: served?.test.metrics.pr_auc ?? service?.test?.pr_auc ?? null,
    postprocessed: postprocessed ? pickMetrics(postprocessed) : null,
    serviceMetrics: service?.service_test ? pickMetrics(service.service_test) : null,
    serviceMode: service?.service_mode ?? null,
    calibration: service?.calibration ?? null,
    unlabeledAlarmsPer100Km2: served?.unlabeled_alarms_per_100km2 ?? null,
  };
}

function domainShift(
  checks: DetectorChecksItem,
  runs: readonly DetectorRunItem[],
): DomainShiftCheck[] {
  const sources = [...new Set(checks.domain_shift.map((run) => run.source_run ?? run.method))];
  return sources.map((source) => {
    const origin = runs.find((run) => run.name === source);
    const home = origin?.data ?? source.split("__")[1];
    const results = checks.domain_shift
      .filter((run) => (run.source_run ?? run.method) === source)
      .sort((a, b) => Number(b.data === home) - Number(a.data === home));
    return {
      source,
      sourceName: origin ? methodName(origin) : source,
      threshold: results[0]?.threshold ?? 0,
      results: results.map((run) => ({
        code: run.name,
        data: run.data,
        metrics: pickMetrics(run.test.metrics),
        metricsCi95: run.test.ci95,
      })),
    };
  });
}

function regionChecks(checks: DetectorChecksItem): RegionCheck[] {
  return checks.leave_region_out.map((item) => {
    const method = item.run.split("__")[0];
    return {
      run: item.run,
      name: METHOD_NAMES[method] ?? item.run,
      protocol: item.protocol,
      regions: item.regions.map((region) => ({
        region: REGION_LABELS[region.region] ?? region.region,
        positives: region.positives,
        metrics: pickMetrics(region.metrics),
      })),
      pooled: pickMetrics(item.pooled),
    };
  });
}

function negativesCheck(checks: DetectorChecksItem): NegativesCheck | null {
  const negatives = checks.black_sea_negatives;
  if (!negatives) return null;
  return {
    run: negatives.run,
    definition: negatives.definition,
    pixels: negatives.pixels,
    alarmPixels: negatives.alarm_pixels,
    polygons: negatives.classes.reduce((sum, item) => sum + item.polygons, 0),
    scenes: new Set(negatives.scenes.map((scene) => scene.scene_id)).size,
    windowZones: negatives.scenes.reduce((sum, scene) => sum + scene.zones, 0),
    classes: negatives.classes.map((item) => ({
      label: NEGATIVE_LABELS[item.label] ?? item.label,
      polygons: item.polygons,
      pixels: item.pixels,
      alarmPixels: item.alarm_pixels,
    })),
  };
}

function detectionRate(item: {
  group: string;
  targets: number;
  detected: number;
  rate: number;
  ci95: readonly [number, number] | null;
  zone_detected: number | null;
}): DetectionRate {
  return {
    group: item.group,
    targets: item.targets,
    detected: item.detected,
    rate: item.rate,
    ci95: item.ci95,
    zoneDetected: item.zone_detected,
  };
}

function plpCheck(checks: DetectorChecksItem): PlpCheck | null {
  const plp = checks.plp;
  if (!plp) return null;
  const group = (key: string) => {
    const item = plp.groups.find((entry) => entry.group === key);
    return item ? detectionRate(item) : null;
  };
  return {
    description: plp.description,
    threshold: plp.threshold,
    targets: plp.targets,
    plastic: group("plastic_or_mixed"),
    natural: group("natural_controls"),
    bySize: plp.by_size.map(detectionRate),
    background: plp.background
      ? {
          windows: plp.background.windows,
          waterKm2: plp.background.water_km2,
          zones: plp.background.zones,
          ringAlarmPixels: plp.background.ring_alarm_pixels,
        }
      : null,
  };
}

function estimate(
  evaluation: ConcentrationItem["profiles"][number]["evaluations"][number] | undefined,
): ConcentrationEstimate | null {
  if (!evaluation) return null;
  const difference = evaluation.difference_mae;
  return {
    report: evaluation.report,
    baselineMae: evaluation.baseline_mae.mean,
    nestedMae: evaluation.nested_mae.mean,
    baselineRmse: evaluation.baseline_rmse.mean,
    nestedRmse: evaluation.nested_rmse.mean,
    difference: difference
      ? { mean: difference.mean, confidence: difference.confidence, ci: difference.ci }
      : null,
    gain: evaluation.gain_over_median,
  };
}

function concentrationProfiles(concentration: ConcentrationItem | null): ConcentrationProfile[] {
  if (!concentration) return [];
  return concentration.profiles.map((profile) => {
    const evaluations = profile.evaluations;
    const primary =
      evaluations.find((item) => item.role === PRIMARY_ROLE) ??
      evaluations.find((item) => item.role !== SHORTLIST_ROLE);
    const shortlist = evaluations.find((item) => item.role === SHORTLIST_ROLE);
    const served = profile.served;
    return {
      profile: profile.profile,
      label: PROFILE_LABELS[profile.profile] ?? profile.profile,
      events: profile.events,
      surveyDays: profile.survey_days,
      primary: estimate(primary),
      shortlist: estimate(shortlist),
      served: served
        ? {
            model: served.model,
            gain: served.gain_over_median,
            value: served.value,
            unit: (served.unit && UNIT_LABELS[served.unit]) ?? served.unit ?? "",
            coverageNominal: served.coverage_nominal,
            coverageEmpirical: served.coverage_empirical,
            reason: served.reason,
          }
        : null,
    };
  });
}

function satelliteLink(concentration: ConcentrationItem | null): SatelliteLinkCheck | null {
  const link = concentration?.satellite_link;
  if (!link) return null;
  const values = link.correlations
    .map((item) => item.p_value)
    .filter((value): value is number => value !== null);
  return {
    events: link.events,
    correlations: link.correlations.length,
    minPValue: values.length ? Math.min(...values) : null,
    pairs: link.pairs.map((pair) => ({
      eventId: pair.event_id,
      sceneId: pair.scene_id,
      concentration: pair.concentration,
      waterPixels: pair.water_pixels,
      detectedShare: pair.detected_share,
      probabilityP99: pair.probability_p99,
      fdiP99: pair.fdi_p99,
    })),
  };
}

function driftSummary(drift: DriftMethodItem | null): DriftMethodSummary | null {
  if (!drift) return null;
  return {
    model: drift.model,
    label: drift.label,
    reason: drift.reason,
    velocity: drift.velocity,
    integration: drift.integration,
    windages: drift.windages,
    stokes: drift.stokes,
    particles: drift.particles,
    members: drift.members,
    diffusivityM2s: drift.diffusivity_m2s,
    horizonsH: drift.horizons_h,
    maxHindcastHours: drift.max_hindcast_hours,
    forcing: [drift.forcing.currents, drift.forcing.waves, ...drift.forcing.wind],
    envelopeSpread: drift.envelope_spread ?? null,
    errors: (drift.validation?.errors ?? []).flatMap((set) =>
      set.horizons.map((horizon) => ({
        label: set.label,
        horizonH: horizon.horizon_h,
        windows: horizon.windows,
        serviceKm: horizon.service_km,
        stationaryKm: horizon.stationary_km,
        persistenceKm: horizon.persistence_km,
      })),
    ),
    coverage: (drift.validation?.calibration?.sets ?? []).flatMap((set) =>
      set.horizons.map((horizon) => ({
        label: set.label,
        horizonH: horizon.horizon_h,
        before: horizon.before,
        after: horizon.after,
      })),
    ),
    nominalCoverage: drift.validation?.calibration?.nominal ?? null,
  };
}

function evidenceOf(
  response: ModelsResponse,
  detector: DetectorItem | null,
  served: DetectorRunItem | null,
  shown: number,
): ModelEvidence {
  return {
    service: detector ? serviceProfile(detector, served) : null,
    otherTestRuns: detector ? detector.runs.length - shown : 0,
    domainShift: detector ? domainShift(detector.checks, detector.runs) : [],
    regions: detector ? regionChecks(detector.checks) : [],
    negatives: detector ? negativesCheck(detector.checks) : null,
    plp: detector ? plpCheck(detector.checks) : null,
    zoneFlags: detector
      ? detector.checks.zone_flags.map((check) => ({
          kind: check.kind,
          title: check.title,
          rule: check.rule,
          inService: check.in_service,
          shares: check.shares,
          discrimination: check.discrimination,
        }))
      : [],
    collection: detector?.checks.collection
      ? {
          alignment: detector.checks.collection.alignment,
          rule: detector.checks.collection.rule,
          chosen: detector.checks.collection.chosen,
          rows: detector.checks.collection.rows.map((row) => ({
            run: row.run,
            inService: row.in_service,
            part: row.part,
            mode: row.mode,
            patches: row.patches,
            scenes: row.scenes,
            c1F1: row.c1_f1,
            c1Ci95: row.c1_ci95,
            l2aF1: row.l2a_f1,
            l2aCi95: row.l2a_ci95,
            difference: row.difference,
            differenceCi95: row.difference_ci95,
          })),
        }
      : null,
    concentration: concentrationProfiles(response.concentration),
    satelliteLink: satelliteLink(response.concentration),
    drift: driftSummary(response.drift),
    sources: response.sources,
  };
}

export function toModelReport(response: ModelsResponse): ModelReport {
  const detector = response.detector;
  const runs = detector ? [...comparableRuns(detector)].sort(byValidation) : [];
  const served = detector?.runs.find((run) => run.in_service) ?? null;
  const classes = reportClasses(runs);
  const evaluationSet = detector
    ? evaluationSetOf(detector, served)
    : { dataset: "MARIDA", split: "test", patches: null, positivePixels: 0, scenes: null };
  const evaluatedOn = `${evaluationSet.dataset} · test`;
  return {
    evaluationSet,
    targetClass: TARGET_CLASS,
    classes,
    models: runs.map((run) => toEvaluation(run, classes, detector?.service ?? null, evaluatedOn)),
    source: MODELS_SOURCE,
    evidence: evidenceOf(response, detector, served, runs.length),
  };
}
