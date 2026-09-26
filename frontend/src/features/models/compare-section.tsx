"use client";

import type { ModelEvaluation } from "@/data/models";
import { SENTINEL2_BANDS, type Sentinel2BandId } from "@/domain/sentinel2";
import { cn } from "@/ui/cn";
import { DemoTag } from "@/ui/demo-mark";
import { PlannedTag } from "@/ui/planned";
import { type BandTint, SpectralRibbon } from "@/ui/spectral-ribbon";
import { StatusTag } from "@/ui/status-tag";
import { METRIC_COPY, METRIC_ORDER, TABLE_HEADS } from "./copy";
import { DASH, formatCi95, formatShare } from "./format";
import { MetricBar } from "./metric-bar";
import { ReportSection } from "./report-section";
import { useReportHint } from "./use-report-hint";

const BAND_IDS = new Set<string>(SENTINEL2_BANDS.map((band) => band.id));

const isBand = (id: string): id is Sentinel2BandId => BAND_IDS.has(id);

function litBands(inputs: readonly string[]): Partial<Record<Sentinel2BandId, BandTint>> {
  return Object.fromEntries(inputs.filter(isBand).map((band) => [band, "index" as const]));
}

const HEAD = "pb-2 text-[12px] leading-4 font-medium text-text-secondary align-bottom";
const CELL = "py-2.5 align-middle @max-4xl:py-0";
const NARROW_LABEL = "text-[11px] leading-[14px] text-text-tertiary @4xl:hidden";

function BandsCell({ inputs }: { inputs: readonly string[] | null }) {
  if (inputs && !inputs.length)
    return (
      <span
        title="Список входов в артефакте прогона не записан"
        className="font-mono text-[13px] leading-[18px] text-text-tertiary"
      >
        {DASH}
      </span>
    );
  const extras = inputs ? inputs.filter((input) => !isBand(input)) : [];
  return (
    <span className="inline-flex items-end gap-1.5">
      <SpectralRibbon lit={inputs ? litBands(inputs) : {}} />
      {extras.length ? (
        <span
          title={extras.join(", ")}
          className="font-mono text-[11px] leading-none text-text-secondary"
        >
          +{extras.length}
        </span>
      ) : null}
    </span>
  );
}

function MetricCells({ model, emphasis }: { model: ModelEvaluation | null; emphasis: boolean }) {
  return METRIC_ORDER.map((key) => {
    const value = model?.metrics[key] ?? null;
    const interval = model?.metricsCi95?.[key] ?? null;
    return (
      <td
        key={key}
        title={
          model
            ? `${METRIC_COPY[key].label} ${formatShare(value)} · ${formatCi95(interval)}`
            : undefined
        }
        className={cn(CELL, "@4xl:pl-4")}
      >
        <span className={NARROW_LABEL}>{METRIC_COPY[key].label}</span>
        <span className="flex items-center gap-2 @4xl:justify-end">
          <span
            className={cn(
              "w-9 font-mono text-[13px] leading-[18px] font-medium @4xl:text-right",
              emphasis ? "text-text-primary" : "text-text-secondary",
              !model && "text-text-tertiary",
            )}
          >
            {formatShare(value)}
          </span>
          <MetricBar value={value} interval={interval} emphasis={emphasis} />
        </span>
      </td>
    );
  });
}

const ROW =
  "border-b border-line-hairline @max-4xl:grid @max-4xl:grid-cols-2 @max-4xl:gap-x-4 @max-4xl:gap-y-2.5 @max-4xl:py-3 @max-4xl:pr-3 @max-4xl:pl-3 @2xl:@max-4xl:grid-cols-4";

function ValidationCell({ value }: { value: number | null }) {
  return (
    <td className={cn(CELL, "@4xl:pl-4 @4xl:text-right")}>
      <span className={NARROW_LABEL}>{TABLE_HEADS.valF1}</span>
      <span className="block font-mono text-[13px] leading-[18px] text-text-secondary">
        {formatShare(value)}
      </span>
    </td>
  );
}

const hasCurve = (model: ModelEvaluation) => model.prCurve.length > 0;

function ModelRow({
  model,
  selected,
  showValidation,
  onSelect,
}: {
  model: ModelEvaluation;
  selected: boolean;
  showValidation: boolean;
  onSelect: () => void;
}) {
  const hint = useReportHint();
  const detail = hasCurve(model) ? "PR-кривая и матрица" : "рабочая точка и матрица";
  const identity = [model.code, model.version].filter(Boolean).join(" · ");
  return (
    <tr
      onClick={onSelect}
      onMouseEnter={() => hint.show(`${model.name} — щелчок: ${detail} этой модели`)}
      onMouseLeave={hint.restore}
      className={cn(
        ROW,
        "cursor-pointer transition-colors duration-[var(--t-2)]",
        selected
          ? "bg-accent-selection-wash @max-4xl:shadow-[inset_3px_0_0_var(--accent-selection)] @4xl:[&>th]:shadow-[inset_3px_0_0_var(--accent-selection)]"
          : "hover:bg-surface-raised",
      )}
    >
      <th
        scope="row"
        className={cn(CELL, "pr-3 pl-3 text-left font-normal @max-4xl:col-span-full @max-4xl:p-0")}
      >
        <button
          type="button"
          aria-pressed={selected}
          onClick={(event) => {
            event.stopPropagation();
            onSelect();
          }}
          className="flex flex-col items-start gap-0.5 text-left focus-visible:outline-offset-4"
        >
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] leading-[18px] font-medium text-text-primary">
            {model.name}
            {model.inUse ? (
              <StatusTag className="h-[18px] px-1.5 text-[11px]">в работе</StatusTag>
            ) : null}
          </span>
          <span
            title={identity}
            className="block w-0 min-w-full truncate font-mono text-[11px] leading-4 text-text-tertiary"
          >
            {identity}
          </span>
        </button>
      </th>
      <td
        className={cn(
          CELL,
          "pr-3 text-[12px] leading-4 text-text-secondary @max-4xl:col-span-full",
        )}
      >
        {model.family}
      </td>
      <MetricCells model={model} emphasis={selected} />
      {showValidation ? <ValidationCell value={model.valF1 ?? null} /> : null}
      <td className={cn(CELL, "@4xl:pl-4 @4xl:text-right")}>
        <span className={NARROW_LABEL}>{TABLE_HEADS.threshold}</span>
        <span className="block font-mono text-[13px] leading-[18px] text-text-secondary">
          {formatShare(model.threshold)}
        </span>
      </td>
      <td
        className={cn(
          CELL,
          showValidation ? "@2xl:@max-4xl:col-span-2" : "@2xl:@max-4xl:col-span-3",
          "@4xl:pr-3 @4xl:pl-5",
        )}
      >
        <span className={cn(NARROW_LABEL, "mb-1 block")}>{TABLE_HEADS.bands}</span>
        <BandsCell inputs={model.inputBands} />
      </td>
    </tr>
  );
}

function PlaceholderRow() {
  return (
    <tr className={ROW}>
      <th
        scope="row"
        className={cn(CELL, "pr-3 pl-3 text-left font-normal @max-4xl:col-span-full @max-4xl:p-0")}
      >
        <span className="flex items-center gap-2 text-[13px] leading-[18px] text-text-secondary">
          Модель детекции
          <PlannedTag capability="model_evaluation" />
        </span>
      </th>
      <td className={cn(CELL, "text-[12px] text-text-tertiary @max-4xl:col-span-full")}>{DASH}</td>
      <MetricCells model={null} emphasis={false} />
      <td className={cn(CELL, "@4xl:pl-4 @4xl:text-right")}>
        <span className={NARROW_LABEL}>{TABLE_HEADS.threshold}</span>
        <span className="block font-mono text-[13px] text-text-tertiary">{DASH}</span>
      </td>
      <td className={cn(CELL, "@2xl:@max-4xl:col-span-3 @4xl:pr-3 @4xl:pl-5")}>
        <span className={cn(NARROW_LABEL, "mb-1 block")}>{TABLE_HEADS.bands}</span>
        <BandsCell inputs={null} />
      </td>
    </tr>
  );
}

type CompareSectionProps = {
  models: readonly ModelEvaluation[];
  selectedId: string | null;
  onSelect: (model: ModelEvaluation) => void;
  isDemo: boolean;
  lede?: string;
  note?: string | null;
};

export function CompareSection({
  models,
  selectedId,
  onSelect,
  isDemo,
  lede,
  note,
}: CompareSectionProps) {
  const showValidation = models.some((model) => model.valF1 !== undefined && model.valF1 !== null);
  const curves = models.some(hasCurve);
  return (
    <ReportSection id="compare" index={2} lede={lede} aside={isDemo ? <DemoTag /> : null}>
      <table className="w-full border-collapse @max-4xl:block">
        <caption className="sr-only">
          Сравнение моделей по классу «мусор»: F1, IoU, Precision, Recall с 95-процентными
          интервалами, рабочий порог и входные каналы Sentinel-2
        </caption>
        <thead className="@max-4xl:sr-only">
          <tr className="border-b border-text-primary">
            <th scope="col" className={cn(HEAD, "pl-3 text-left")}>
              {TABLE_HEADS.model}
            </th>
            <th scope="col" className={cn(HEAD, "text-left")}>
              {TABLE_HEADS.architecture}
            </th>
            {METRIC_ORDER.map((key) => (
              <th key={key} scope="col" className={cn(HEAD, "pl-4 text-right")}>
                <span className="pr-[64px]">{METRIC_COPY[key].label}</span>
              </th>
            ))}
            {showValidation ? (
              <th scope="col" className={cn(HEAD, "pl-4 text-right whitespace-nowrap")}>
                {TABLE_HEADS.valF1}
              </th>
            ) : null}
            <th scope="col" className={cn(HEAD, "pl-4 text-right")}>
              {TABLE_HEADS.threshold}
            </th>
            <th scope="col" className={cn(HEAD, "pr-3 pl-5 text-left whitespace-nowrap")}>
              {TABLE_HEADS.bands}
            </th>
          </tr>
        </thead>
        <tbody className="@max-4xl:block @max-4xl:border-t @max-4xl:border-text-primary">
          {models.length ? (
            models.map((model) => (
              <ModelRow
                key={model.id}
                model={model}
                selected={model.id === selectedId}
                showValidation={showValidation}
                onSelect={() => onSelect(model)}
              />
            ))
          ) : (
            <PlaceholderRow />
          )}
        </tbody>
      </table>
      <p className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] leading-4 text-text-tertiary">
        <span className="inline-flex items-center gap-1.5">
          <svg width={28} height={10} aria-hidden className="shrink-0">
            <rect width={20} height={5} className="fill-text-secondary" />
            <path
              d="M14.5 8.5H26.5M14.5 6.5V10M26.5 6.5V10"
              className="stroke-text-tertiary"
              fill="none"
            />
          </svg>
          значение и 95{" "}% ДИ
        </span>
        <span className="inline-flex items-center gap-1.5">
          <SpectralRibbon lit={{ B04: "index", B08: "index" }} showTitles={false} />
          выделенные ячейки — каналы на входе модели
        </span>
        {models.length ? (
          <span>
            щелчок по строке — {curves ? "кривая" : "рабочая точка"} и матрица этой модели в разделе
            3
          </span>
        ) : null}
        {note ? <span>{note}</span> : null}
      </p>
    </ReportSection>
  );
}
