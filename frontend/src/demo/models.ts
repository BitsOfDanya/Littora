import type { Interval, MetricKey, ModelEvaluation, ModelReport } from "@/data/models";
import type { ClassificationMetrics, ConfusionMatrix, PrCurvePoint } from "@/domain/model";

const CLASSES = ["Мусор", "Саргассум", "Пена", "Судно/след", "Вода"] as const;

const CLASS_PIXELS = [812, 2460, 1180, 940, 18400] as const;

const MISSED_DEBRIS_SHARE = [0, 0.42, 0.3, 0.1, 0.18] as const;

const FALSE_DEBRIS_SHARE = [0, 0.45, 0.32, 0.15, 0.08] as const;

const BASE_CONFUSION: readonly (readonly number[])[] = [
  [0, 0, 0, 0, 0],
  [0, 0, 0.02, 0.01, 0.09],
  [0, 0.02, 0, 0.07, 0.09],
  [0, 0.01, 0.08, 0, 0.07],
  [0, 0.004, 0.006, 0.005, 0],
];

const S2_INPUT_BANDS = [
  "B01",
  "B02",
  "B03",
  "B04",
  "B05",
  "B06",
  "B07",
  "B08",
  "B8A",
  "B11",
  "B12",
] as const;

const Z_95 = 1.959964;

const EFFECTIVE_SAMPLE = 330;

type OperatingPoint = {
  threshold: number;
  precision: number;
  recall: number;
  prior: number;
  spreadPositive: number;
  spreadNegative: number;
};

function erf(x: number): number {
  const sign = x < 0 ? -1 : 1;
  const a = Math.abs(x);
  const t = 1 / (1 + 0.3275911 * a);
  const poly =
    ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t;
  return sign * (1 - poly * Math.exp(-a * a));
}

const normalCdf = (z: number) => 0.5 * (1 + erf(z / Math.SQRT2));

function normalQuantile(p: number): number {
  let low = -8;
  let high = 8;
  for (let step = 0; step < 80; step += 1) {
    const mid = (low + high) / 2;
    if (normalCdf(mid) < p) low = mid;
    else high = mid;
  }
  return (low + high) / 2;
}

const logit = (p: number) => Math.log(p / (1 - p));

const round = (value: number, digits = 3) => Math.round(value * 10 ** digits) / 10 ** digits;

function curveFor(point: OperatingPoint): PrCurvePoint[] {
  const z = logit(point.threshold);
  const falsePositiveRate =
    (point.prior * point.recall * (1 / point.precision - 1)) / (1 - point.prior);
  const meanPositive = z - point.spreadPositive * normalQuantile(1 - point.recall);
  const meanNegative = z - point.spreadNegative * normalQuantile(1 - falsePositiveRate);
  return Array.from({ length: 97 }, (_, index) => {
    const threshold = round(0.02 + index * 0.01, 2);
    const t = logit(threshold);
    const recall = 1 - normalCdf((t - meanPositive) / point.spreadPositive);
    const fpr = 1 - normalCdf((t - meanNegative) / point.spreadNegative);
    const truePositive = point.prior * recall;
    const falsePositive = (1 - point.prior) * fpr;
    const precision =
      truePositive + falsePositive > 0 ? truePositive / (truePositive + falsePositive) : 1;
    return { threshold, precision: round(precision), recall: round(recall) };
  });
}

function metricsFor(point: OperatingPoint): ClassificationMetrics {
  const f1 = (2 * point.precision * point.recall) / (point.precision + point.recall);
  return {
    f1: round(f1),
    iou: round(f1 / (2 - f1)),
    precision: point.precision,
    recall: point.recall,
  };
}

function wilson(value: number, sample: number): Interval {
  const z2 = Z_95 * Z_95;
  const denominator = 1 + z2 / sample;
  const centre = (value + z2 / (2 * sample)) / denominator;
  const half =
    (Z_95 * Math.sqrt((value * (1 - value)) / sample + z2 / (4 * sample * sample))) / denominator;
  return [round(centre - half, 2), round(centre + half, 2)];
}

function intervalsFor(metrics: ClassificationMetrics): Record<MetricKey, Interval> {
  return {
    f1: wilson(metrics.f1, EFFECTIVE_SAMPLE),
    iou: wilson(metrics.iou, EFFECTIVE_SAMPLE),
    precision: wilson(metrics.precision, EFFECTIVE_SAMPLE),
    recall: wilson(metrics.recall, EFFECTIVE_SAMPLE),
  };
}

function split(total: number, shares: readonly number[]): number[] {
  const raw = shares.map((share) => share * total);
  const floors = raw.map(Math.floor);
  let remainder = total - floors.reduce((sum, value) => sum + value, 0);
  const order = raw
    .map((value, index) => ({ index, fraction: value - Math.floor(value) }))
    .sort((a, b) => b.fraction - a.fraction);
  for (const { index } of order) {
    if (remainder <= 0) break;
    floors[index] += 1;
    remainder -= 1;
  }
  return floors;
}

function confusionFor(point: OperatingPoint, errorScale: number): ConfusionMatrix {
  const truePositive = Math.round(point.recall * CLASS_PIXELS[0]);
  const missed = split(CLASS_PIXELS[0] - truePositive, MISSED_DEBRIS_SHARE);
  const falseDebris = split(
    Math.round(truePositive / point.precision - truePositive),
    FALSE_DEBRIS_SHARE,
  );
  const counts = CLASS_PIXELS.map((total, row) => {
    if (row === 0) return [truePositive, ...missed.slice(1)];
    const cells = BASE_CONFUSION[row].map((share) => Math.round(share * errorScale * total));
    cells[0] = falseDebris[row];
    cells[row] = total - cells.reduce((sum, value) => sum + value, 0);
    return cells;
  });
  return { labels: CLASSES, counts };
}

type ModelSeed = Omit<
  ModelEvaluation,
  "threshold" | "metrics" | "metricsCi95" | "prCurve" | "confusion" | "evaluatedOn"
> & { operating: OperatingPoint; errorScale: number };

function evaluate({ operating, errorScale, ...seed }: ModelSeed): ModelEvaluation {
  const metrics = metricsFor(operating);
  return {
    ...seed,
    threshold: operating.threshold,
    metrics,
    metricsCi95: intervalsFor(metrics),
    evaluatedOn: "MARIDA · test",
    prCurve: curveFor(operating),
    confusion: confusionFor(operating, errorScale),
  };
}

const SEEDS: readonly ModelSeed[] = [
  {
    id: "rf-spectral",
    code: "rf-spectral",
    name: "Спектральный базовый классификатор (RF)",
    family: "Random Forest · пиксельный",
    task: "pixel_classification",
    version: "0.0-demo",
    inUse: false,
    inputBands: [...S2_INPUT_BANDS, "FDI", "NDVI", "FAI"],
    trainingData: ["marida"],
    knownFailureModes: ["Саргассум", "Пена", "Солнечный блик"],
    operating: {
      threshold: 0.5,
      precision: 0.62,
      recall: 0.55,
      prior: 0.12,
      spreadPositive: 1.7,
      spreadNegative: 1.35,
    },
    errorScale: 1.6,
  },
  {
    id: "unetpp",
    code: "unetpp-r34",
    name: "U-Net++",
    family: "U-Net++ · энкодер ResNet-34",
    task: "segmentation",
    version: "0.0-demo",
    inUse: false,
    inputBands: S2_INPUT_BANDS,
    trainingData: ["marida", "mados"],
    knownFailureModes: ["Судовые следы", "Края облаков"],
    operating: {
      threshold: 0.45,
      precision: 0.69,
      recall: 0.63,
      prior: 0.12,
      spreadPositive: 1.6,
      spreadNegative: 1.3,
    },
    errorScale: 1.25,
  },
  {
    id: "marinext",
    code: "MariNeXt-S2",
    name: "MariNeXt",
    family: "SegNeXt (MSCAN) · обучена на MADOS",
    task: "segmentation",
    version: "0.0-demo",
    inUse: true,
    inputBands: S2_INPUT_BANDS,
    trainingData: ["mados", "marida"],
    knownFailureModes: ["Тонкие нити уже пикселя"],
    operating: {
      threshold: 0.5,
      precision: 0.74,
      recall: 0.69,
      prior: 0.12,
      spreadPositive: 1.5,
      spreadNegative: 1.3,
    },
    errorScale: 1,
  },
  {
    id: "segformer",
    code: "segformer-b2",
    name: "SegFormer-B2",
    family: "SegFormer · энкодер MiT-B2",
    task: "segmentation",
    version: "0.0-demo",
    inUse: false,
    inputBands: S2_INPUT_BANDS,
    trainingData: ["mados"],
    knownFailureModes: ["Мутная прибрежная вода"],
    operating: {
      threshold: 0.45,
      precision: 0.7,
      recall: 0.68,
      prior: 0.12,
      spreadPositive: 1.55,
      spreadNegative: 1.3,
    },
    errorScale: 1.1,
  },
];

export const DEMO_MODEL_REPORT: ModelReport = {
  evaluationSet: {
    dataset: "MARIDA",
    split: "test",
    patches: 359,
    positivePixels: CLASS_PIXELS[0],
  },
  targetClass: "Мусор",
  classes: CLASSES,
  models: SEEDS.map(evaluate),
  source: "demo/models.ts",
};
