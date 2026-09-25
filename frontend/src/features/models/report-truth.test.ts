import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { EvaluationSet, ModelEvaluation } from "@/data/models";
import { CompareSection } from "./compare-section";
import { MATRIX_CLASSES } from "./copy";
import { DatasetsSection } from "./datasets-section";
import { LimitationsSection } from "./limitations-section";
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
