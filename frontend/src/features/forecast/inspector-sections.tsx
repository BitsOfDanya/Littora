"use client";

import type { ReactNode } from "react";
import type { BeachSegmentRisk, DriftForecastDetail, ForecastRun } from "@/data/forecast";
import type { ForecastHorizonH } from "@/domain/forecast";
import { Readout, ReadoutGrid } from "@/features/inspector/parts/readout-grid";
import { formatLatitude, formatLongitude } from "@/lib/format/coordinates";
import { formatNumber } from "@/lib/format/numbers";
import { formatUtcDateTime } from "@/lib/format/time";
import { cn } from "@/ui/cn";
import { SeverityGlyph } from "@/ui/indicators";
import { KeyValue, KeyValueList } from "@/ui/key-value";
import { PlannedTag } from "@/ui/planned";
import { PanelSection } from "@/ui/section";
import {
  CAUTION_FROM_H,
  horizonLabel,
  meanSpeedMs,
  type Reliability,
  RELIABILITY_WORD,
  shiftIso,
} from "./drift-math";
import {
  formatAxes,
  formatCourse,
  formatEstimate,
  formatKm,
  formatKm2,
  formatProbability,
  formatWindow,
} from "./forecast-copy";
import { type HorizonRow, horizonRows } from "./forecast-model";

const NNBSP = " ";

export const SECTION_IDS = {
  position: "forecast-position",
  horizons: "forecast-horizons",
  beaching: "forecast-beaching",
  source: "forecast-source",
  conditions: "forecast-conditions",
} as const;

export function ReliabilityBars({ reliability }: { reliability: Reliability }) {
  const level = reliability === "high" ? 3 : reliability === "medium" ? 2 : 1;
  return (
    <span aria-hidden className="inline-flex items-end gap-px">
      {[1, 2, 3].map((step) => (
        <span
          key={step}
          className={cn(
            "block h-2 w-[3px] border border-text-secondary",
            step <= level ? "bg-text-secondary" : "bg-transparent",
          )}
        />
      ))}
    </span>
  );
}

function CautionNote({ children }: { children: ReactNode }) {
  return (
    <p
      role="note"
      className="flex items-start gap-2 rounded-[var(--radius-ctl)] bg-state-caution-wash px-2.5 py-2 text-[12px] leading-4 text-state-caution"
    >
      <SeverityGlyph severity="caution" size={14} className="mt-px shrink-0" />
      <span>{children}</span>
    </p>
  );
}

function CoordinateValue({ lng, lat }: { lng: number; lat: number }) {
  return (
    <span className="flex flex-col text-[13px] leading-[18px] font-medium">
      <span>{formatLatitude(lat, "dm")}</span>
      <span>{formatLongitude(lng, "dm")}</span>
    </span>
  );
}

export function PositionSection({
  forecast,
  run,
  row,
  isDemo,
}: {
  forecast: DriftForecastDetail;
  run: ForecastRun;
  row: HorizonRow;
  isDemo: boolean;
}) {
  const [top] = forecast.beaching;
  const speed = meanSpeedMs(row.displacement.distanceM, row.horizonH);
  return (
    <PanelSection
      id={SECTION_IDS.position}
      index="01"
      title="Положение на горизонте"
      aside={
        <span className="font-mono text-[12px] font-semibold text-accent-selection">
          {horizonLabel(row.horizonH)}
        </span>
      }
    >
      <ReadoutGrid>
        <Readout
          label="Центр"
          value={<CoordinateValue lng={row.median[0]} lat={row.median[1]} />}
          note={`медиана ансамбля · цель ${formatUtcDateTime(shiftIso(run.t0, row.horizonH))}`}
        />
        <Readout
          label="Смещение"
          value={formatNumber(row.displacement.distanceM / 1_000, 1)}
          unit="км"
          interval={`${formatCourse(row.displacement.bearingDeg)} · от T₀`}
          note={`в среднем ${formatNumber(speed, 2)}${NNBSP}м/с`}
        />
        <Readout
          label={`Эллипс 90${NNBSP}%`}
          value={formatAxes(row.ellipse.majorAxisM, row.ellipse.minorAxisM).replace(
            `${NNBSP}км`,
            "",
          )}
          unit="км"
          interval={`площадь ${formatKm2(row.ellipse.areaM2)}`}
          note={`${formatNumber(run.ensembleSize)} траекторий ансамбля`}
        />
        <Readout
          label={`Вынос на берег до +72${NNBSP}ч`}
          value={formatProbability(forecast.beachingAny.value)}
          interval={`90${NNBSP}% ДИ ${formatProbability(forecast.beachingAny.low)}–${formatProbability(forecast.beachingAny.high)}`}
          note={top ? `${top.name} · ${formatWindow(top.windowH)}` : "берег не достигнут"}
        />
      </ReadoutGrid>
      {row.horizonH >= CAUTION_FROM_H ? (
        <CautionNote>
          Достоверность снижается после +48{NNBSP}ч. Используйте облако, а не линию медианы
        </CautionNote>
      ) : null}
      <p className="text-[11px] leading-4 text-text-tertiary">
        {isDemo
          ? "Источник: фикстура demo/forecast · поле течений синтетическое · модель дрейфа не подключена"
          : `Источник: прогон ${formatUtcDateTime(run.runAt)} · ${run.model}`}
      </p>
    </PanelSection>
  );
}

const TABLE_HEAD = ["Гор.", "Смещение", "Курс", "Облако, км²", "Выброс", "Надёжность"] as const;

export function HorizonsSection({
  forecast,
  horizonH,
  onChoose,
}: {
  forecast: DriftForecastDetail;
  horizonH: ForecastHorizonH;
  onChoose: (horizonH: ForecastHorizonH) => void;
}) {
  const rows = horizonRows(forecast);
  return (
    <PanelSection id={SECTION_IDS.horizons} index="02" title="По горизонтам">
      <table className="w-full border-collapse text-[12px]">
        <caption className="sr-only">Прогноз по горизонтам +6…+72 ч</caption>
        <thead>
          <tr className="border-b border-line-hairline text-left text-[11px] text-text-tertiary">
            {TABLE_HEAD.map((head, index) => (
              <th
                key={head}
                scope="col"
                className={cn("h-7 pr-1.5 font-normal", index > 0 && index < 5 && "text-right")}
              >
                {head}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const current = row.horizonH === horizonH;
            return (
              <tr
                key={row.horizonH}
                onClick={() => onChoose(row.horizonH)}
                aria-selected={current}
                className={cn(
                  "h-7 cursor-pointer border-b border-line-hairline font-mono text-text-primary hover:bg-surface-raised",
                  current && "bg-accent-selection-wash hover:bg-accent-selection-wash",
                )}
              >
                <th
                  scope="row"
                  className={cn(
                    "border-l-[3px] border-transparent pr-1.5 pl-1.5 text-left font-medium",
                    current && "border-accent-selection text-accent-selection",
                  )}
                >
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      onChoose(row.horizonH);
                    }}
                    aria-pressed={current}
                    className="rounded-[var(--radius-ctl)] whitespace-nowrap"
                  >
                    {horizonLabel(row.horizonH)}
                  </button>
                </th>
                <td className="pr-1.5 text-right whitespace-nowrap">
                  {formatKm(row.displacement.distanceM)}
                </td>
                <td className="pr-1.5 text-right whitespace-nowrap">
                  {formatCourse(row.displacement.bearingDeg)}
                </td>
                <td className="pr-1.5 text-right">
                  {formatNumber(
                    row.ellipse.areaM2 / 1_000_000,
                    row.ellipse.areaM2 < 10_000_000 ? 1 : 0,
                  )}
                </td>
                <td className="pr-1.5 text-right">{formatProbability(row.beachedShare)}</td>
                <td className="font-sans">
                  <span className="inline-flex items-center gap-1.5 text-text-secondary">
                    <ReliabilityBars reliability={row.reliability} />
                    {row.reliability === "low" ? "низкая" : RELIABILITY_WORD[row.reliability]}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="text-[11px] leading-4 text-text-tertiary">
        Смещение и курс — медианы от центра пятна на T₀; облако — эллипс 90{NNBSP}% ансамбля; выброс
        — доля траекторий, достигших берега к этому сроку. Низкая надёжность — только ориентир.
      </p>
    </PanelSection>
  );
}

function severityGlyph(risk: BeachSegmentRisk) {
  return <SeverityGlyph severity={risk.severity} size={14} className="shrink-0" />;
}

export function BeachingSection({
  forecast,
  run,
  onFocus,
}: {
  forecast: DriftForecastDetail;
  run: ForecastRun;
  onFocus: (risk: BeachSegmentRisk) => void;
}) {
  return (
    <PanelSection id={SECTION_IDS.beaching} index="03" title="Риск выноса на берег">
      {forecast.beaching.length ? (
        <ol className="flex flex-col">
          {forecast.beaching.map((risk, index) => {
            const focusable = risk.path.length > 1;
            return (
              <li key={risk.id} className="border-b border-line-hairline last:border-b-0">
                <button
                  type="button"
                  disabled={!focusable}
                  onClick={() => onFocus(risk)}
                  className={cn(
                    "flex w-full items-start gap-2 rounded-[var(--radius-ctl)] py-1.5 text-left hover:bg-surface-raised disabled:hover:bg-transparent",
                    risk.severity === "info" && "text-text-secondary",
                  )}
                  title={focusable ? "Показать участок на карте" : undefined}
                >
                  <span className="w-3 pt-px font-mono text-[11px] text-text-tertiary">
                    {index + 1}
                  </span>
                  <span className="pt-px">{severityGlyph(risk)}</span>
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="text-[13px] leading-[18px] font-medium">{risk.name}</span>
                    <span className="text-[11px] leading-4 text-text-tertiary">
                      {formatWindow(risk.windowH)} · {risk.members} из {run.ensembleSize}
                    </span>
                  </span>
                  <span className="pt-px font-mono text-[13px] whitespace-nowrap">
                    {formatEstimate(risk.probability)}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="text-[12px] text-text-secondary">
          До +72{NNBSP}ч ни одна из {run.ensembleSize} траекторий не дошла до берега.
        </p>
      )}
      <p className="text-[11px] leading-4 text-text-tertiary">
        Вероятность — доля траекторий ансамбля до +72{NNBSP}ч, в скобках 90{NNBSP}% ДИ. ⬣ тревога от
        0,40 · △ внимание от 0,10.
      </p>
    </PanelSection>
  );
}

export function SourceSection({ forecast }: { forecast: DriftForecastDetail }) {
  return (
    <PanelSection
      id={SECTION_IDS.source}
      index="04"
      title="Вероятный источник"
      aside={
        <span className="font-mono text-[11px] text-text-tertiary">
          обратный дрейф {horizonLabel(-(forecast.hindcastPath.length - 1))}
        </span>
      }
    >
      <ol className="flex flex-col">
        {forecast.sources.map((source) => (
          <li
            key={source.id}
            className={cn(
              "flex min-h-7 items-center gap-3 border-b border-line-hairline last:border-b-0",
              !source.position && "text-text-secondary",
            )}
          >
            <span className="min-w-0 flex-1 text-[13px] leading-4">{source.name}</span>
            <span aria-hidden className="h-1.5 w-16 bg-surface-sunken">
              <span
                className="block h-full bg-text-secondary"
                style={{ width: `${Math.round(source.probability.value * 100)}%` }}
              />
            </span>
            <span className="w-28 text-right font-mono text-[12px] whitespace-nowrap">
              {formatEstimate(source.probability)}
            </span>
          </li>
        ))}
      </ol>
      <p className="text-[11px] leading-4 text-text-tertiary">
        Доля обратных траекторий, пришедших к устью (радиус 5{NNBSP}км) за 48{NNBSP}ч. Это не
        установление виновника, а подсказка для проверки.
      </p>
    </PanelSection>
  );
}

export function ConditionsSection({ run, isDemo }: { run: ForecastRun; isDemo: boolean }) {
  const rows: readonly [string, string][] = [
    ["Течения", run.currents],
    ["Ветер", run.wind],
    ["Парусность", `${formatNumber(run.windageRatio * 100)}${NNBSP}%`],
    ["Ансамбль", `${formatNumber(run.ensembleSize)} частиц`],
    ["Модель", run.model],
  ];
  return (
    <PanelSection id={SECTION_IDS.conditions} index="05" title="Условия расчёта">
      <KeyValueList>
        {rows.map(([label, value]) => (
          <KeyValue key={label} label={label} tag={<PlannedTag capability="drift_forecast" />}>
            {value}
          </KeyValue>
        ))}
      </KeyValueList>
      {isDemo ? (
        <p className="text-[11px] leading-4 text-text-tertiary">
          Сейчас в макете: синтетическое поле течений и ветер {formatNumber(run.windSpeedMs)}
          {NNBSP}м/с с {formatNumber(run.windFromDeg)}° — не расчёт {run.model}. Поле течений и
          частицы — синтетические, для макета.
        </p>
      ) : null}
    </PanelSection>
  );
}
