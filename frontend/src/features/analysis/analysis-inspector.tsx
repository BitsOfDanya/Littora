"use client";

import { findAoi } from "@/config/aois";
import { useDemoActive } from "@/features/cartouche/use-layer-truth";
import { CopyButton } from "@/features/inspector/dossier/copy-button";
import { InspectorFrame } from "@/features/inspector/parts/inspector-frame";
import { ShellSlot } from "@/features/shell/shell-slots";
import { type Analysis, analysisFileUrl } from "@/lib/api/analyses";
import { formatUtcDateTime } from "@/lib/format/time";
import { useAnalysisStore } from "@/state/analysis-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { buttonClasses } from "@/ui/button";
import { IconDownload } from "@/ui/icons";
import { StatusTag } from "@/ui/status-tag";
import { CONCENTRATION_UNIT, STATUS_TONES } from "./analysis-copy";
import { HistorySection } from "./history-section";
import { MeasurementsSection } from "./measurements-section";
import { RequestSection } from "./request-section";
import { PendingResult, ResultSection, SceneQualitySection } from "./result-sections";
import {
  useCaseTargets,
  useCurrentAnalysis,
  useOpenSavedMatch,
  useSurveySceneDefault,
} from "./use-analysis";

function PanelHeader({ aoiName, analysis }: { aoiName: string; analysis: Analysis | null }) {
  const targets = useCaseTargets().data;
  const targetKey = useAnalysisStore((state) => state.targetKey);
  const key = analysis?.target.key ?? targetKey ?? targets?.primary;
  const title = targets?.targets.find((target) => target.key === key)?.title;
  return (
    <div className="flex flex-col gap-1.5">
      <p className="font-serif text-[20px] leading-6 font-medium text-text-primary italic">
        {aoiName}
      </p>
      <p className="text-[12px] leading-4 text-text-secondary">
        {title ?? "Целевая величина кейса"} ·{" "}
        <span className="font-mono text-text-primary">{CONCENTRATION_UNIT}</span>
      </p>
      {analysis ? (
        <span className="flex flex-wrap gap-1.5 pt-0.5">
          <StatusTag tone={STATUS_TONES[analysis.status.status]}>{analysis.status.label}</StatusTag>
          <StatusTag tone={STATUS_TONES[analysis.concentration.status]}>
            {analysis.concentration.label}
          </StatusTag>
        </span>
      ) : null}
    </div>
  );
}

function shareUrl(analysis: Analysis): string {
  const params = new URLSearchParams(window.location.search);
  if (analysis.request.aoi_id) params.set("aoi", analysis.request.aoi_id);
  params.set("analysis", analysis.id);
  return `${window.location.origin}${window.location.pathname}?${params.toString()}`;
}

function ExportBar({ analysis }: { analysis: Analysis }) {
  return (
    <div className="flex w-full flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <a
          className={buttonClasses("default", "md")}
          href={analysisFileUrl(analysis.id, "export.geojson")}
          download
        >
          <IconDownload size={14} />
          GeoJSON
        </a>
        <a
          className={buttonClasses("default", "md")}
          href={analysisFileUrl(analysis.id, "export.csv")}
          download
        >
          <IconDownload size={14} />
          CSV
        </a>
        <span className="ml-auto inline-flex items-center gap-1 text-[12px] text-text-secondary">
          ссылка
          <CopyButton value={shareUrl(analysis)} label="Скопировать ссылку на анализ" />
        </span>
      </div>
      <p className="font-mono text-[11px] leading-[14px] text-text-tertiary">
        анализ {analysis.id} · конвейер v{analysis.pipeline_version} ·{" "}
        {formatUtcDateTime(analysis.computed_at)}
      </p>
    </div>
  );
}

function AnalysisPanel() {
  const aoi = findAoi(useWorkspaceStore((state) => state.aoiId));
  const setPanelOpen = useAnalysisStore((state) => state.setPanelOpen);
  const current = useCurrentAnalysis();
  const analysis = current.data ?? null;
  const aoiName = aoi?.name ?? "Район";

  return (
    <InspectorFrame
      label="Анализ района"
      eyebrow="Анализ района · Sentinel-2 L2A"
      crumbs={[{ label: aoiName, serif: true }, { label: "Анализ" }]}
      onClose={() => setPanelOpen(false)}
      header={<PanelHeader aoiName={aoiName} analysis={analysis} />}
      footer={analysis ? <ExportBar analysis={analysis} /> : undefined}
    >
      <RequestSection analysis={analysis} />
      {analysis ? (
        <>
          <ResultSection analysis={analysis} />
          <SceneQualitySection analysis={analysis} />
        </>
      ) : (
        <PendingResult isLoading={current.isFetching} error={current.error} />
      )}
      <MeasurementsSection hasAnalysis={analysis !== null} />
      <HistorySection />
    </InspectorFrame>
  );
}

export function AnalysisInspector() {
  const selectedCandidate = useWorkspaceStore((state) => state.selectedCandidateId);
  const panelOpen = useAnalysisStore((state) => state.panelOpen);
  const demoActive = useDemoActive();
  useSurveySceneDefault();
  useOpenSavedMatch();

  if (selectedCandidate || demoActive || !panelOpen) return null;
  return (
    <ShellSlot region="inspector">
      <AnalysisPanel />
    </ShellSlot>
  );
}
