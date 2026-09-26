"use client";

import { useState } from "react";
import { type ModelEvaluation, type ModelEvidence, useModelReportSource } from "@/data/models";
import { pluralRu } from "@/features/shell/orientation/plural";
import { ShellSlot } from "@/features/shell/shell-slots";
import { ChecksSection, hasChecks } from "./checks-section";
import { CompareSection } from "./compare-section";
import { ConcentrationSection } from "./concentration-section";
import { API_LEDE, MATRIX_CLASSES, MATRIX_COPY } from "./copy";
import { DatasetsSection } from "./datasets-section";
import { DriftSection } from "./drift-section";
import { GallerySection, ReadingGuide } from "./guide-sections";
import { PairsSection } from "./pairs-section";
import { formatCount } from "./format";
import { LimitationsSection } from "./limitations-section";
import { PipelineSection } from "./pipeline-section";
import { ReportHeader, ReportPlannedState } from "./report-header";
import { ReportScrim, ReportSheet } from "./report-sheet";
import { SummarySection } from "./summary-section";
import { ThresholdSection } from "./threshold-section";
import { useReportBaseHint } from "./use-report-hint";

const TITLE_ID = "models-report-title";

const FIRST_EXTRA_INDEX = 5;

type Selection = { modelId: string; threshold: number };

export function confusionLede(model: ModelEvaluation | null): string | undefined {
  const errors = model?.falsePositivesByClass;
  if (!errors) return undefined;
  if (!errors.length) return "На размеченном фоне test ложных срабатываний нет.";
  const top = errors
    .slice(0, 3)
    .map((row) => `${row.label} (${formatCount(row.falsePositives)})`)
    .join(", ");
  return `Больше всего ложных пикселей на test: ${top}. Доли по группам классов — в матрице справа.`;
}

export function otherRunsNote(evidence: ModelEvidence | undefined): string | null {
  const count = evidence?.otherTestRuns ?? 0;
  if (!count) return null;
  return `Ещё ${count} ${pluralRu(count, ["прогон", "прогона", "прогонов"])} посчитаны на другом наборе test — с этой таблицей не сравнимы.`;
}

export function ModelsReport() {
  const { report, fetch } = useModelReportSource();
  useReportBaseHint();
  const data = report.origin === "none" ? null : report.data;
  const isDemo = report.origin === "demo";
  const evidence = report.origin === "api" ? report.data.evidence : undefined;
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

  const showChecks = evidence ? hasChecks(evidence) : false;
  const showConcentration = Boolean(evidence?.concentration.length);
  const drift = evidence?.drift ?? null;
  const checksIndex = FIRST_EXTRA_INDEX;
  const concentrationIndex = checksIndex + Number(showChecks);
  const pairs = evidence?.satelliteLink?.pairs.length ? evidence.satelliteLink : null;
  const pairsIndex = concentrationIndex + Number(showConcentration);
  const driftIndex = pairsIndex + Number(pairs !== null);
  const datasetsIndex = driftIndex + Number(drift !== null);

  return (
    <ShellSlot region="map-overlay">
      <ReportScrim />
      <ReportSheet titleId={TITLE_ID}>
        <ReportHeader titleId={TITLE_ID} isDemo={isDemo} sources={evidence?.sources} />
        {report.origin === "none" ? <ReportPlannedState fetch={fetch} /> : null}
        {evidence ? <ReadingGuide index={0} /> : null}
        <SummarySection
          model={inUse}
          evaluationSet={data?.evaluationSet ?? null}
          isDemo={isDemo}
          service={evidence?.service ?? null}
        />
        <CompareSection
          models={models}
          selectedId={selected?.id ?? null}
          onSelect={selectModel}
          isDemo={isDemo}
          lede={evidence && models.length ? API_LEDE.compare : undefined}
          note={otherRunsNote(evidence)}
        />
        <ThresholdSection
          model={selected}
          threshold={threshold}
          onThreshold={changeThreshold}
          classes={data?.classes ?? MATRIX_CLASSES}
          isDemo={isDemo}
          lede={evidence ? confusionLede(selected) : undefined}
          matrixNote={evidence ? MATRIX_COPY.apiGrouping : undefined}
        />
        {evidence ? <GallerySection index={4} /> : null}
        {evidence && showChecks ? <ChecksSection evidence={evidence} index={checksIndex} /> : null}
        {evidence && showConcentration ? (
          <ConcentrationSection
            profiles={evidence.concentration}
            link={evidence.satelliteLink}
            index={concentrationIndex}
          />
        ) : null}
        {pairs ? <PairsSection link={pairs} index={pairsIndex} /> : null}
        {drift ? <DriftSection drift={drift} index={driftIndex} /> : null}
        <DatasetsSection index={datasetsIndex} />
        <LimitationsSection index={datasetsIndex + 1} />
        {evidence ? null : <PipelineSection index={datasetsIndex + 2} />}
      </ReportSheet>
    </ShellSlot>
  );
}
