"use client";

import type { ModelReportFetch } from "@/data/models";
import { useApiMeta, useCapability } from "@/features/system/use-capabilities";
import { apiUrl } from "@/lib/api/client";
import { useWorkspaceStore } from "@/state/workspace-store";
import { Button } from "@/ui/button";
import { cn } from "@/ui/cn";
import { DemoRibbon, DemoTag } from "@/ui/demo-mark";
import { IconAlarm, IconDownload } from "@/ui/icons";
import { PlannedState, PlannedTag } from "@/ui/planned";
import { Caps } from "@/ui/section";
import { REPORT_COPY } from "./copy";
import styles from "./report.module.css";

const CAPABILITY = "model_evaluation";

function CapabilityMark() {
  const meta = useApiMeta();
  const availability = useCapability(CAPABILITY);
  if (meta.isError)
    return (
      <span className="inline-flex items-center gap-1 text-state-alarm">
        <IconAlarm size={12} />
        ошибка
      </span>
    );
  if (meta.isPending) return <span>проверяем…</span>;
  if (availability === "available") return <span>готово</span>;
  return <PlannedTag capability={CAPABILITY} />;
}

function PdfAction({ isDemo }: { isDemo: boolean }) {
  const availability = useCapability(CAPABILITY);
  if (isDemo || availability !== "available")
    return (
      <span title={REPORT_COPY.pdfWhy} className="inline-flex items-center gap-2">
        <Button disabled icon={<IconDownload />} aria-describedby="models-pdf-why">
          {REPORT_COPY.pdf}
        </Button>
        <PlannedTag capability={CAPABILITY} />
        <span id="models-pdf-why" className="sr-only">
          {REPORT_COPY.pdfWhy}
        </span>
      </span>
    );
  const printable = apiUrl("/models/report.html?print=true");
  const standalone = apiUrl("/models/report.html?download=true");
  return (
    <span className="inline-flex items-center gap-2">
      <Button
        icon={<IconDownload />}
        title={REPORT_COPY.pdfHow}
        onClick={() => window.open(printable, "_blank", "noopener")}
      >
        {REPORT_COPY.pdf}
      </Button>
      <a
        href={standalone}
        className="text-[12px] text-text-secondary underline underline-offset-2 hover:text-text-primary"
      >
        HTML
      </a>
    </span>
  );
}

const CAPABILITY_LINE =
  "flex flex-wrap items-center gap-x-1.5 gap-y-1 px-4 py-2 font-mono text-[11px] text-text-tertiary @2xl:px-8";

type ReportHeaderProps = {
  titleId: string;
  isDemo: boolean;
  sources?: readonly string[];
};

export function ReportHeader({ titleId, isDemo, sources }: ReportHeaderProps) {
  return (
    <>
      <header className="px-4 pt-6 pb-5 @2xl:px-8 @2xl:pt-8 @2xl:pb-6">
        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
          <Caps>{REPORT_COPY.eyebrow}</Caps>
          <PdfAction isDemo={isDemo} />
        </div>
        <h1
          id={titleId}
          className={cn(
            "mt-3 font-serif text-[34px] leading-[40px] font-normal text-text-primary not-italic",
            styles.h1,
          )}
        >
          {REPORT_COPY.title}
        </h1>
        {isDemo ? (
          <p className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-text-secondary">
            <DemoTag label={REPORT_COPY.demoTag} />
            <span>{REPORT_COPY.sample}</span>
          </p>
        ) : null}
      </header>
      {isDemo ? (
        <>
          <DemoRibbon source="demo/models.ts" className="@2xl:px-8" />
          <p className={CAPABILITY_LINE}>
            <span>{CAPABILITY}</span>
            <span aria-hidden>·</span>
            <CapabilityMark />
            <span className="font-sans text-[12px]">— {REPORT_COPY.note}</span>
          </p>
        </>
      ) : null}
      {!isDemo && sources ? (
        <p
          className={cn(CAPABILITY_LINE, "border-t border-line-hairline")}
          title={sources.join("\n")}
        >
          <span>{CAPABILITY}</span>
          <span aria-hidden>·</span>
          <CapabilityMark />
          <span className="font-sans text-[12px]">
            — {REPORT_COPY.apiNote}, артефактов: {sources.length}
          </span>
          <span aria-hidden>·</span>
          <span>GET /api/v1/models</span>
        </p>
      ) : null}
    </>
  );
}

function ReportFetchError({ message, retry }: { message: string; retry: () => void }) {
  return (
    <section className="flex max-w-[720px] flex-col gap-2 rounded-[var(--radius-ctl)] border border-dashed border-line-control bg-surface-panel p-4">
      <h3 className="flex items-center gap-2 text-[13px] font-semibold text-text-primary">
        <IconAlarm size={14} className="shrink-0 text-state-alarm" />
        {REPORT_COPY.errorTitle}
      </h3>
      <p className="text-[13px] text-state-alarm">{message}</p>
      <p className="font-mono text-[11px] text-text-tertiary">GET /api/v1/models</p>
      <div className="pt-1">
        <Button onClick={retry}>{REPORT_COPY.retry}</Button>
      </div>
    </section>
  );
}

export function ReportPlannedState({ fetch }: { fetch?: ModelReportFetch }) {
  if (fetch?.status === "loading")
    return (
      <div className="px-4 pb-7 @2xl:px-8 @2xl:pb-8">
        <p aria-live="polite" className="text-[13px] text-text-secondary">
          {REPORT_COPY.loading}
        </p>
      </div>
    );
  if (fetch?.status === "error")
    return (
      <div className="px-4 pb-7 @2xl:px-8 @2xl:pb-8">
        <ReportFetchError message={fetch.message} retry={fetch.retry} />
      </div>
    );
  return <ReportCapabilityState />;
}

function ReportCapabilityState() {
  const meta = useApiMeta();
  const demoFixtures = useWorkspaceStore((state) => state.demoFixtures);
  const setDemoFixtures = useWorkspaceStore((state) => state.setDemoFixtures);
  const status = meta.isPending ? "loading" : meta.isError ? "error" : "planned";
  const action =
    status === "error" ? (
      <Button onClick={() => void meta.refetch()}>{REPORT_COPY.retry}</Button>
    ) : demoFixtures ? null : (
      <Button onClick={() => setDemoFixtures(true)} title="Включить демо-фикстуры · D">
        {REPORT_COPY.showDemo}
      </Button>
    );
  return (
    <div className="px-4 pb-7 @2xl:px-8 @2xl:pb-8">
      <PlannedState
        title={REPORT_COPY.plannedTitle}
        capability={CAPABILITY}
        status={status}
        requirement={REPORT_COPY.plannedRequirement}
        action={action}
        className="max-w-[720px]"
      >
        {REPORT_COPY.plannedBody}
      </PlannedState>
    </div>
  );
}
