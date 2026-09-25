"use client";

import { useState } from "react";
import { type ModelEvaluation, useModelReport } from "@/data/models";
import { ShellSlot } from "@/features/shell/shell-slots";
import { CompareSection } from "./compare-section";
import { MATRIX_CLASSES } from "./copy";
import { DatasetsSection } from "./datasets-section";
import { LimitationsSection } from "./limitations-section";
import { PipelineSection } from "./pipeline-section";
import { ReportHeader, ReportPlannedState } from "./report-header";
import { ReportScrim, ReportSheet } from "./report-sheet";
import { SummarySection } from "./summary-section";
import { ThresholdSection } from "./threshold-section";
import { useReportBaseHint } from "./use-report-hint";

const TITLE_ID = "models-report-title";

type Selection = { modelId: string; threshold: number };

export function ModelsReport() {
  const report = useModelReport();
  useReportBaseHint();
  const data = report.origin === "none" ? null : report.data;
  const isDemo = report.origin === "demo";
  const models = data?.models ?? [];
  const inUse = models.find((model) => model.inUse) ?? models[0] ?? null;
  const [selection, setSelection] = useState<Selection | null>(null);
  const selected = models.find((model) => model.id === selection?.modelId) ?? inUse;
  const threshold =
    selected && selection?.modelId === selected.id
      ? selection.threshold
      : (selected?.threshold ?? null);

  const selectModel = (model: ModelEvaluation) =>
    setSelection((current) =>
      current?.modelId === model.id ? current : { modelId: model.id, threshold: model.threshold },
    );
  const changeThreshold = (value: number) => {
    if (selected) setSelection({ modelId: selected.id, threshold: value });
  };

  return (
    <ShellSlot region="map-overlay">
      <ReportScrim />
      <ReportSheet titleId={TITLE_ID}>
        <ReportHeader titleId={TITLE_ID} isDemo={isDemo} />
        {report.origin === "none" ? <ReportPlannedState /> : null}
        <SummarySection model={inUse} evaluationSet={data?.evaluationSet ?? null} isDemo={isDemo} />
        <CompareSection
          models={models}
          selectedId={selected?.id ?? null}
          onSelect={selectModel}
          isDemo={isDemo}
        />
        <ThresholdSection
          model={selected}
          threshold={threshold}
          onThreshold={changeThreshold}
          classes={data?.classes ?? MATRIX_CLASSES}
          isDemo={isDemo}
        />
        <DatasetsSection />
        <LimitationsSection />
        <PipelineSection />
      </ReportSheet>
    </ShellSlot>
  );
}
