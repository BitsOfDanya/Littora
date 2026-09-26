import type { EvaluationSet, ModelEvaluation, ServiceProfile } from "@/data/models";
import type { ClassificationMetrics } from "@/domain/model";
import { DemoTag } from "@/ui/demo-mark";
import { API_LEDE, METRIC_COPY, METRIC_ORDER } from "./copy";
import { formatCi95, formatCount, formatShare, NARROW_NBSP } from "./format";
import { ReportSection } from "./report-section";

type SummarySectionProps = {
  model: ModelEvaluation | null;
  evaluationSet: EvaluationSet | null;
  isDemo: boolean;
  service?: ServiceProfile | null;
};

const identity = (model: ModelEvaluation) =>
  [model.code, model.version].filter(Boolean).join(" · ");

function SampleSize({ evaluationSet }: { evaluationSet: EvaluationSet }) {
  const parts = [
    evaluationSet.patches !== null ? [formatCount(evaluationSet.patches), "патчей"] : null,
    evaluationSet.scenes ? [formatCount(evaluationSet.scenes), "сцен"] : null,
    [formatCount(evaluationSet.positivePixels), "пикс. мусора"],
  ].filter((part): part is string[] => part !== null);
  return (
    <span>
      {evaluationSet.dataset}, {evaluationSet.split}:{" "}
      {parts.map(([value, unit], index) => (
        <span key={unit}>
          {index ? ", " : null}
          <span className="font-mono">{value}</span>
          {NARROW_NBSP}
          {unit}
        </span>
      ))}
    </span>
  );
}

function MetricsInline({ metrics }: { metrics: ClassificationMetrics }) {
  return (
    <>
      P <span className="font-mono">{formatShare(metrics.precision)}</span> · R{" "}
      <span className="font-mono">{formatShare(metrics.recall)}</span> · F1{" "}
      <span className="font-mono">{formatShare(metrics.f1)}</span> · IoU{" "}
      <span className="font-mono">{formatShare(metrics.iou)}</span>
    </>
  );
}

function ServiceLine({ service }: { service: ServiceProfile }) {
  const post = service.postprocessed;
  return (
    <>
      {service.serviceMetrics ? (
        <p className="text-text-primary">
          В сервисе на том же test: <MetricsInline metrics={service.serviceMetrics} />
          {service.serviceMode ? ` — ${service.serviceMode}` : null}.
        </p>
      ) : null}
      {post ? (
        <p>
          {service.serviceMetrics ? "Исследовательская оценка с TTA" : "С постобработкой сервиса"}{" "}
          (зоны от <span className="font-mono">{service.minPixels}</span>
          {NARROW_NBSP}пикс.): <MetricsInline metrics={post} />.
        </p>
      ) : null}
      {service.calibration ? <p>Вероятность в интерфейсе: {service.calibration}.</p> : null}
      {service.unlabeledAlarmsPer100Km2 !== null ? (
        <p>
          На неразмеченной воде test —{" "}
          <span className="font-mono">
            {formatCount(Math.round(service.unlabeledAlarmsPer100Km2))}
          </span>
          {NARROW_NBSP}пикс. срабатываний на 100{NARROW_NBSP}км²; в метрики они не входят.
        </p>
      ) : null}
    </>
  );
}

function ContextLine({
  model,
  evaluationSet,
  isDemo,
  service,
}: Omit<SummarySectionProps, "service"> & { service: ServiceProfile | null }) {
  if (!model || !evaluationSet)
    return (
      <p className="mt-4 text-[12px] leading-4 text-text-tertiary">
        Модель, порог и выборка появятся после первого прогона оценки.
      </p>
    );
  return (
    <div className="mt-4 flex flex-col gap-1 text-[12px] leading-4 text-text-secondary">
      <p className="flex flex-wrap gap-x-2">
        <span className="font-mono text-text-primary">{identity(model)}</span>
        <span aria-hidden>·</span>
        <span>класс «мусор»</span>
        <span aria-hidden>·</span>
        <span>
          порог <span className="font-mono">{formatShare(model.threshold)}</span>
        </span>
        <span aria-hidden>·</span>
        <SampleSize evaluationSet={evaluationSet} />
      </p>
      {service ? <ServiceLine service={service} /> : null}
      <p className="text-text-tertiary">
        {isDemo
          ? `95${NARROW_NBSP}% ДИ в отчёте — бутстреп по патчам; здесь показаны демо-значения.`
          : `95${NARROW_NBSP}% ДИ — бутстреп по сценам test. Модель, порог и постобработка выбраны на валидации, test посчитан один раз.`}
      </p>
    </div>
  );
}

export function SummarySection({ model, evaluationSet, isDemo, service }: SummarySectionProps) {
  return (
    <ReportSection
      id="summary"
      index={1}
      lede={isDemo || !model ? undefined : API_LEDE.summary}
      aside={isDemo ? <DemoTag /> : null}
    >
      <dl className="grid grid-cols-12 gap-x-6 gap-y-5">
        {METRIC_ORDER.map((key) => {
          const value = model?.metrics[key] ?? null;
          const interval = model?.metricsCi95?.[key] ?? null;
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
      <ContextLine
        model={model}
        evaluationSet={evaluationSet}
        isDemo={isDemo}
        service={service ?? null}
      />
    </ReportSection>
  );
}
