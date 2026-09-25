"use client";

import type { Sourced } from "@/domain/data-origin";
import type { ClassificationMetrics, ModelCard } from "@/domain/model";
import { DEMO_MODEL_REPORT } from "@/demo/models";
import { useDemoSourced } from "./use-sourced";

export type MetricKey = keyof ClassificationMetrics;

export type Interval = readonly [low: number, high: number];

export type ModelEvaluation = ModelCard & {
  code: string;
  inUse: boolean;
  metricsCi95: Readonly<Record<MetricKey, Interval>>;
};

export type EvaluationSet = {
  dataset: string;
  split: string;
  patches: number;
  positivePixels: number;
};

export type ModelReport = {
  evaluationSet: EvaluationSet;
  targetClass: string;
  classes: readonly string[];
  models: readonly ModelEvaluation[];
  source: string;
};

export function useModelReport(): Sourced<ModelReport> {
  return useDemoSourced(DEMO_MODEL_REPORT, { aoiScoped: false });
}
