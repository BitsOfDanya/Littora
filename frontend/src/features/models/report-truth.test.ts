import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PREDICTED_CLASSES } from "@/data/model-report";
import type {
  ConcentrationProfile,
  DriftMethodSummary,
  EvaluationSet,
  ModelEvaluation,
  ModelEvidence,
  ServiceProfile,
} from "@/data/models";
import { ChecksSection } from "./checks-section";
import { CompareSection } from "./compare-section";
import { ConcentrationSection } from "./concentration-section";
import { MATRIX_CLASSES, MATRIX_COPY, PR_COPY } from "./copy";
import { DatasetsSection } from "./datasets-section";
import { DriftSection } from "./drift-section";
import { NARROW_NBSP } from "./format";
import { LimitationsSection } from "./limitations-section";
import { confusionLede, otherRunsNote } from "./models-report";
import { ReportHeader } from "./report-header";
import { SummarySection } from "./summary-section";
import { ThresholdSection } from "./threshold-section";

const MODEL: ModelEvaluation = {
  id: "m",
  code: "M-1",
  name: "Модель",
  family: "U-Net",
  task: "segmentation",
  version: "0.0-demo",
  inUse: true,
  inputBands: ["B02", "B03", "B04", "B08", "FDI"],
  trainingData: ["marida"],
  threshold: 0.5,
  metrics: { f1: 0.71, iou: 0.56, precision: 0.74, recall: 0.69 },
  metricsCi95: {
    f1: [0.66, 0.76],
    iou: [0.5, 0.61],
    precision: [0.69, 0.78],
    recall: [0.64, 0.74],
  },
  evaluatedOn: "MARIDA · test",
  prCurve: [
    { threshold: 0.3, precision: 0.6, recall: 0.8 },
    { threshold: 0.5, precision: 0.74, recall: 0.69 },
    { threshold: 0.7, precision: 0.86, recall: 0.5 },
  ],
  confusion: {
    labels: MATRIX_CLASSES,
    counts: MATRIX_CLASSES.map((_, row) => MATRIX_CLASSES.map((__, col) => (row === col ? 90 : 2))),
  },
  knownFailureModes: [],
};

const EVALUATION: EvaluationSet = {
  dataset: "MARIDA",
  split: "test",
  patches: 359,
  positivePixels: 812,
};

const render = (element: ReactElement) =>
  renderToStaticMarkup(createElement(QueryClientProvider, { client: new QueryClient() }, element));

const noop = () => undefined;

describe("Models report truth marking", () => {
  it("marks every fixture-built section with ДЕМО", () => {
    const panels = [
      render(
        createElement(SummarySection, { model: MODEL, evaluationSet: EVALUATION, isDemo: true }),
      ),
      render(
        createElement(CompareSection, {
          models: [MODEL],
          selectedId: "m",
          onSelect: noop,
          isDemo: true,
        }),
      ),
      render(
        createElement(ThresholdSection, {
          model: MODEL,
          threshold: 0.5,
          onThreshold: noop,
          classes: MATRIX_CLASSES,
          isDemo: true,
        }),
      ),
    ];
    for (const html of panels) expect(html).toContain("ДЕМО");
  });

  it("puts the ribbon and the ДЕМО-МЕТРИКИ tag on the report header", () => {
    const html = render(createElement(ReportHeader, { titleId: "t", isDemo: true }));
    expect(html).toContain("ДЕМО-МЕТРИКИ");
    expect(html).toContain("Фикстура интерфейса — не результат модели");
    expect(html).toContain("demo/models.ts");
  });

  it("keeps the real reference sections free of ДЕМО", () => {
    expect(render(createElement(DatasetsSection))).not.toContain("ДЕМО");
    expect(render(createElement(LimitationsSection))).not.toContain("ДЕМО");
  });

  it("shows dashes instead of numbers when there is no evaluation", () => {
    const summary = render(
      createElement(SummarySection, { model: null, evaluationSet: null, isDemo: false }),
    );
    expect(summary).not.toContain("ДЕМО");
    expect(summary).toContain("95 % ДИ —");
    const header = render(createElement(ReportHeader, { titleId: "t", isDemo: false }));
    expect(header).not.toContain("ДЕМО");
    const compare = render(
      createElement(CompareSection, {
        models: [],
        selectedId: null,
        onSelect: noop,
        isDemo: false,
      }),
    );
    expect(compare).toContain("план");
    expect(compare).not.toContain("0,71");
  });
});

const API_CLASSES = ["Мусор", "Судно/след", "Вода"] as const;

const API_MODEL: ModelEvaluation = {
  ...MODEL,
  id: "raunet__marida_mixed__common",
  code: "raunet__marida_mixed__common",
  name: "RA-U-Net, BCE + Dice, MARIDA + L2A",
  version: "конфиг 2e01de9b",
  inputBands: [],
  threshold: 0.159,
  metrics: { f1: 0.898, iou: 0.815, precision: 0.836, recall: 0.97 },
  metricsCi95: null,
  prCurve: [],
  confusion: {
    labels: API_CLASSES,
    predicted: PREDICTED_CLASSES,
    counts: [
      [290, 9],
      [28, 2660],
      [4, 50605],
    ],
  },
  valF1: 0.943,
  prAuc: 0.976,
  falsePositivesByClass: [
    { label: "суда", pixels: 1163, falsePositives: 24 },
    { label: "волны", pixels: 1865, falsePositives: 14 },
  ],
};

const SERVICE: ServiceProfile = {
  code: "raunet__marida_mixed__common",
  threshold: 0.159,
  thresholdSource: "val_max_f1",
  minPixels: 2,
  bands: ["B02", "B08"],
  seaMask: null,
  validation: null,
  tta: true,
  prAuc: 0.976,
  postprocessed: { f1: 0.902, iou: 0.821, precision: 0.856, recall: 0.953 },
  serviceMetrics: { f1: 0.91, iou: 0.835, precision: 0.874, recall: 0.95 },
  serviceMode: "без TTA",
  calibration: null,
  unlabeledAlarmsPer100Km2: 247.4,
};

const PROFILE: ConcentrationProfile = {
  profile: "S2_visual_GT2",
  label: "S2 · пластик, визуально",
  events: 63,
  surveyDays: 26,
  primary: {
    report: "broad",
    baselineMae: 34.1,
    nestedMae: 30.8,
    baselineRmse: 47.4,
    nestedRmse: 43.7,
    difference: { mean: -3.31, confidence: 0.95, ci: [-9.28, 3.76] },
    gain: false,
  },
  shortlist: null,
  served: {
    model: "median",
    gain: false,
    value: 36.09,
    unit: "шт./км²",
    coverageNominal: 0.8,
    coverageEmpirical: 0.819,
    reason: null,
  },
};

const DRIFT: DriftMethodSummary = {
  model: "littora-drift-1",
  label: "сценарий дрейфа",
  reason: "сценарий, а не проверенный прогноз",
  velocity: "u = u_теч + α·U10",
  integration: "RK2, шаг 900 с",
  windages: [0.005, 0.01, 0.02, 0.03],
  stokes: [true, false],
  particles: 40,
  members: 320,
  diffusivityM2s: 5,
  horizonsH: [6, 12, 24, 48, 72],
  maxHindcastHours: 48,
  forcing: ["SMOC", "MFWAM", "ERA5"],
  envelopeSpread: null,
  errors: [],
  coverage: [],
  nominalCoverage: null,
};

const EVIDENCE: ModelEvidence = {
  service: SERVICE,
  otherTestRuns: 4,
  domainShift: [
    {
      source: "raunet__marida",
      sourceName: "RA-U-Net, BCE + Dice, MARIDA (ACOLITE)",
      threshold: 0.706,
      results: [
        {
          code: "on_marida",
          data: "marida",
          metrics: { f1: 0.858, iou: 0.752, precision: 0.781, recall: 0.953 },
          metricsCi95: null,
        },
        {
          code: "on_l2a",
          data: "marida_l2a",
          metrics: { f1: 0.798, iou: 0.665, precision: 0.962, recall: 0.682 },
          metricsCi95: null,
        },
      ],
    },
  ],
  regions: [],
  negatives: {
    run: "raunet__marida_mixed__common",
    definition: null,
    pixels: 488727,
    alarmPixels: 1,
    polygons: 45,
    scenes: 5,
    windowZones: 81,
    classes: [{ label: "суда", polygons: 7, pixels: 455, alarmPixels: 1 }],
  },
  plp: {
    description: null,
    threshold: null,
    targets: 53,
    plastic: {
      group: "plastic_or_mixed",
      targets: 37,
      detected: 6,
      rate: 0.162,
      ci95: [0.077, 0.311],
      zoneDetected: 4,
    },
    natural: null,
    bySize: [],
    background: null,
  },
  zoneFlags: [
    {
      kind: "unstable",
      title: "«неустойчива к поворотам»",
      rule: "зона выше порога меньше чем в 84,9 % из 8 видов",
      inService: true,
      shares: [
        { part: "test", group: "обломки", objects: 157, flagged: 13, share: 0.083 },
        { part: "test", group: "ложные размеченные", objects: 14, flagged: 6, share: 0.429 },
      ],
      discrimination: [
        { part: "val", measure: "AUC согласия", value: 0.696, ci95: [0.586, 0.967] },
      ],
    },
  ],
  collection: {
    alignment: "C1 есть для 35 сцен MARIDA; точно совмещены с разметкой 8",
    rule: "объектный F1 на объединённой val",
    chosen: "raunet__marida_mixed__common",
    rows: [
      {
        run: "raunet__marida_mixed__common",
        inService: true,
        part: "test",
        mode: "объекты, допуск 1 пикс.",
        patches: 116,
        scenes: 5,
        c1F1: 0.947,
        c1Ci95: [0.85, 0.99],
        l2aF1: 0.948,
        l2aCi95: null,
        difference: -0.002,
        differenceCi95: [-0.072, 0.047],
      },
    ],
  },
  serviceByRegion: {
    run: "raunet__marida_mixed__common",
    part: "test",
    description: "Модель обучалась на всех регионах train — это не проверка на новом регионе.",
    regions: [
      {
        region: "Гондурас",
        scenes: 9,
        patches: 263,
        debrisPixels: 205,
        metrics: { precision: 0.866, recall: 0.976, f1: 0.917, iou: 0.847 },
      },
      {
        region: "Индонезия",
        scenes: 1,
        patches: 26,
        debrisPixels: 41,
        metrics: { precision: 0.661, recall: 0.902, f1: 0.763, iou: 0.617 },
      },
    ],
    pooled: {
      region: "all",
      scenes: 13,
      patches: 312,
      debrisPixels: 299,
      metrics: { precision: 0.836, recall: 0.97, f1: 0.898, iou: 0.815 },
    },
  },
  concentration: [PROFILE],
  satelliteLink: { events: 7, correlations: 7, minPValue: 0.26, pairs: [] },
  drift: DRIFT,
  sources: ["models/detector/service/detector.json"],
};

describe("Models report on evaluation artifacts", () => {
  it("renders the service model without ДЕМО and with the real interval method", () => {
    const summary = render(
      createElement(SummarySection, {
        model: API_MODEL,
        evaluationSet: { ...EVALUATION, patches: 312, positivePixels: 299, scenes: 13 },
        isDemo: false,
        service: SERVICE,
      }),
    );
    expect(summary).not.toContain("ДЕМО");
    expect(summary).not.toContain("демо-значения");
    expect(summary).toContain("бутстреп по сценам");
    expect(summary).toContain("0,90");
    expect(summary).toContain(`95${NARROW_NBSP}% ДИ —`);
    const header = render(
      createElement(ReportHeader, { titleId: "t", isDemo: false, sources: EVIDENCE.sources }),
    );
    expect(header).not.toContain("ДЕМО");
    expect(header).toContain("GET /api/v1/models");
  });

  it("shows validation F1 and says which runs are left out of the comparison", () => {
    const html = render(
      createElement(CompareSection, {
        models: [API_MODEL],
        selectedId: API_MODEL.id,
        onSelect: noop,
        isDemo: false,
        note: otherRunsNote(EVIDENCE),
      }),
    );
    expect(html).toContain("F1 val");
    expect(html).toContain("0,94");
    expect(html).toContain("Ещё 4 прогона");
    expect(html).toContain("рабочая точка");
    expect(html).not.toContain("ДЕМО");
  });

  it("marks the missing PR curve and draws a two-column matrix", () => {
    const html = render(
      createElement(ThresholdSection, {
        model: API_MODEL,
        threshold: API_MODEL.threshold,
        onThreshold: noop,
        classes: API_CLASSES,
        isDemo: false,
        lede: confusionLede(API_MODEL),
        matrixNote: MATRIX_COPY.apiGrouping,
      }),
    );
    expect(html).toContain("P 0,84 · R 0,97");
    expect(html).toContain("Не мусор");
    expect(html).toContain("суда (24)");
    expect(html).toContain("PR-AUC");
    expect(html).not.toContain(PR_COPY.legendChosen);
    expect(html).not.toContain("ДЕМО");
  });

  it("renders checks, concentration and drift from the report", () => {
    const checks = render(createElement(ChecksSection, { evidence: EVIDENCE, index: 4 }));
    expect(checks).toContain("Сдвиг домена");
    expect(checks).toContain("−0,060");
    expect(checks).toContain("6 из 37");
    expect(checks).toContain("81 зону");
    expect(checks).toContain("Флаг «неустойчива к поворотам»");
    expect(checks).toContain("13 из 157");
    expect(checks).toContain("Коллекция сервиса C1");
    expect(checks).toContain("116 патчей, 5 сцен");
    expect(checks).toContain("Сервисная модель по регионам test");
    expect(checks).toContain("Индонезия");
    expect(checks).toContain("0,76");
    expect(checks).toContain("Весь test");
    expect(checks).toContain("0,70");
    const concentration = render(
      createElement(ConcentrationSection, {
        profiles: EVIDENCE.concentration,
        link: EVIDENCE.satelliteLink,
        index: 5,
      }),
    );
    expect(concentration).toContain("−3,3 [−9,3; +3,8]");
    expect(concentration).toContain("выигрыш не значим");
    expect(concentration).toContain("медиана");
    expect(concentration).toContain("значимой связи нет");
    const drift = render(createElement(DriftSection, { drift: DRIFT, index: 6 }));
    expect(drift).toContain("0,5, 1, 2, 3");
    expect(drift).toContain("320 на зону");
    for (const html of [checks, concentration, drift]) expect(html).not.toContain("ДЕМО");
  });
});
