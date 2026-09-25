import type { EvaluationSet, ModelEvaluation } from "@/data/models";
import { DemoTag } from "@/ui/demo-mark";
import { METRIC_COPY, METRIC_ORDER } from "./copy";
import { formatCi95, formatCount, formatShare, NARROW_NBSP } from "./format";
import { ReportSection } from "./report-section";

type SummarySectionProps = {
  model: ModelEvaluation | null;
  evaluationSet: EvaluationSet | null;
  isDemo: boolean;
};

function ContextLine({ model, evaluationSet }: Omit<SummarySectionProps, "isDemo">) {
  if (!model || !evaluationSet)
    return (
      <p className="mt-4 text-[12px] leading-4 text-text-tertiary">
        Модель, порог и выборка появятся после первого прогона оценки.
      </p>
    );
  return (
    <div className="mt-4 flex flex-col gap-1 text-[12px] leading-4 text-text-secondary">
      <p className="flex flex-wrap gap-x-2">
        <span className="font-mono text-text-primary">
          {model.code} · {model.version}
        </span>
        <span aria-hidden>·</span>
        <span>класс «мусор»</span>
        <span aria-hidden>·</span>
        <span>
          порог <span className="font-mono">{formatShare(model.threshold)}</span>
        </span>
        <span aria-hidden>·</span>
        <span>
          {evaluationSet.dataset}, {evaluationSet.split}:{" "}
          <span className="font-mono">{formatCount(evaluationSet.patches)}</span> патчей,{" "}
          <span className="font-mono">{formatCount(evaluationSet.positivePixels)}</span>
          {NARROW_NBSP}пикс. мусора
        </span>
      </p>
      <p className="text-text-tertiary">
        95{NARROW_NBSP}% ДИ в отчёте — бутстреп по патчам; здесь показаны демо-значения.
      </p>
    </div>
  );
}

export function SummarySection({ model, evaluationSet, isDemo }: SummarySectionProps) {
  return (
    <ReportSection id="summary" index={1} aside={isDemo ? <DemoTag /> : null}>
      <dl className="grid grid-cols-12 gap-x-6 gap-y-5">
        {METRIC_ORDER.map((key) => {
          const value = model?.metrics[key] ?? null;
          const interval = model?.metricsCi95[key] ?? null;
          return (
            <div
              key={key}
              className="col-span-6 flex flex-col border-t border-text-primary pt-2.5 @3xl:col-span-3"
            >
              <dt className="flex flex-col gap-0.5">
                <span className="text-[12px] leading-4 font-semibold text-text-secondary">
                  {METRIC_COPY[key].label}
                </span>
                <span className="text-[12px] leading-4 text-text-tertiary">
                  {METRIC_COPY[key].gloss}
                </span>
              </dt>
              <dd className="mt-3 font-mono text-[26px] leading-[30px] font-medium text-text-primary">
                {formatShare(value)}
              </dd>
              <dd className="mt-1 font-mono text-[11px] leading-4 text-text-secondary">
                {formatCi95(interval)}
              </dd>
            </div>
          );
        })}
      </dl>
      <ContextLine model={model} evaluationSet={evaluationSet} />
    </ReportSection>
  );
}
