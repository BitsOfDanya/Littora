export type ModelTask = "pixel_classification" | "segmentation" | "coverage_regression";

export type ClassificationMetrics = {
  f1: number;
  iou: number;
  precision: number;
  recall: number;
};

export type PrCurvePoint = {
  threshold: number;
  precision: number;
  recall: number;
};

export type ConfusionMatrix = {
  labels: readonly string[];
  counts: readonly (readonly number[])[];
};

export type ModelCard = {
  id: string;
  name: string;
  family: string;
  task: ModelTask;
  version: string;
  inputBands: readonly string[];
  trainingData: readonly string[];
  threshold: number;
  metrics: ClassificationMetrics;
  evaluatedOn: string;
  prCurve: readonly PrCurvePoint[];
  confusion: ConfusionMatrix;
  knownFailureModes: readonly string[];
};
