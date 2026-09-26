"use client";

import type { ModelEvaluation } from "@/data/models";
import { DemoTag } from "@/ui/demo-mark";
import { Caps } from "@/ui/section";
import { MATRIX_COPY, PR_COPY } from "./copy";
import { ConfusionMatrix } from "./confusion-matrix";
import { formatShare } from "./format";
import { PrChart } from "./pr-chart";
import { ReportSection } from "./report-section";
import { PrLegend, ThresholdControl } from "./threshold-control";

type ThresholdSectionProps = {
  model: ModelEvaluation | null;
  threshold: number | null;
  onThreshold: (value: number) => void;
  classes: readonly string[];
  isDemo: boolean;
  lede?: string;
  matrixNote?: string;
};

function PanelHead({ title, detail }: { title: string; detail?: string | null }) {
  return (
    <div className="mb-3 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
      <Caps>{title}</Caps>
      {detail ? <span className="text-[12px] text-text-secondary">{detail}</span> : null}
    </div>
  );
}

export function ThresholdSection({
  model,
  threshold,
  onThreshold,
  classes,
  isDemo,
  lede,
  matrixNote,
}: ThresholdSectionProps) {
  const prAuc = model?.prAuc ?? null;
  return (
    <ReportSection id="threshold" index={3} lede={lede} aside={isDemo ? <DemoTag /> : null}>
      <div className="grid grid-cols-12 gap-x-8 gap-y-8">
        <figure className="col-span-12 m-0 min-w-0 @4xl:col-span-6">
          <PanelHead title={PR_COPY.title} detail={model ? model.name : null} />
          <PrChart model={model} threshold={threshold} onThreshold={onThreshold} />
          <ThresholdControl model={model} threshold={threshold} onThreshold={onThreshold} />
          {model ? <PrLegend model={model} /> : null}
          {prAuc !== null ? (
            <p className="mt-2 pl-[44px] text-[12px] leading-4 text-text-tertiary max-md:pl-0">
              PR-AUC на test:{" "}
              <span className="font-mono text-text-secondary">{formatShare(prAuc)}</span>
            </p>
          ) : null}
        </figure>
        <figure className="col-span-12 m-0 min-w-0 @4xl:col-span-6 @4xl:border-l @4xl:border-line-hairline @4xl:pl-8">
          <PanelHead
            title={MATRIX_COPY.title}
            detail={model ? `${model.name} · порог ${formatShare(model.threshold)}` : null}
          />
          <ConfusionMatrix model={model} classes={classes} note={matrixNote} />
        </figure>
      </div>
    </ReportSection>
  );
}
