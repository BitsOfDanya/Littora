"use client";

import type { ReactNode } from "react";
import type { CandidatePass } from "@/data/timeline";
import type { SceneSummary } from "@/domain/scene";
import { useSelectObject } from "@/features/objects/use-select-object";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { formatNumber, formatPercent, formatSigned } from "@/lib/format/numbers";
import { useWorkspaceStore } from "@/state/workspace-store";
import { Button } from "@/ui/button";
import { Checkbox } from "@/ui/checkbox";
import { cn } from "@/ui/cn";
import { SeverityGlyph } from "@/ui/indicators";
import { PlannedTag } from "@/ui/planned";
import { PanelSection } from "@/ui/section";
import {
  cloudText,
  formatCoverage,
  formatCoverageInterval,
  formatKm2,
  formatPp,
  objectsCount,
} from "./compare-format";
import {
  type ComparePair,
  dayMonth,
  isUsable,
  type ObjectRow,
  type SideTotals,
} from "./compare-model";
import { DeltaBar, DeltaLegend } from "./delta-bar";

const NUMBER_CELL = "px-1.5 text-right font-mono text-[13px] whitespace-nowrap";

function SummaryRow({
  label,
  a,
  b,
  delta,
}: {
  label: string;
  a: ReactNode;
  b: ReactNode;
  delta: ReactNode;
}) {
  return (
    <tr className="h-7 border-b border-line-hairline align-baseline last:border-b-0">
      <th scope="row" className="py-1 pr-2 text-left text-[12px] font-normal text-text-secondary">
        {label}
      </th>
      <td className={cn(NUMBER_CELL, "py-1 text-text-primary")}>{a}</td>
      <td className={cn(NUMBER_CELL, "py-1 text-text-primary")}>{b}</td>
      <td className={cn(NUMBER_CELL, "py-1 pr-0 text-text-secondary")}>{delta}</td>
    </tr>
  );
}

function CoverageCell({ totals }: { totals: SideTotals }) {
  if (!totals.coverage) return <span className="text-text-tertiary">—</span>;
  return (
    <span className="inline-flex flex-col items-end leading-4">
      {formatCoverage(totals.coverage.value)}
      <span className="text-[11px] text-text-tertiary">
        {formatCoverageInterval(totals.coverage)}
      </span>
    </span>
  );
}

function IncompleteNote({
  letter,
  scene,
  totals,
}: {
  letter: "A" | "B";
  scene: SceneSummary;
  totals: SideTotals;
}) {
  const hidden = totals.hidden
    ? `под облаками ${objectsCount(totals.hidden)} из отслеживаемых`
    : "скопления в закрытой части могли не попасть в итог";
  return (
    <p className="flex items-start gap-1.5 text-[12px] leading-4 text-state-caution">
      <SeverityGlyph severity="caution" size={12} className="mt-0.5" />
      <span>
        {letter}: {cloudText(scene)} — итог по {letter} неполный, {hidden}.
      </span>
    </p>
  );
}

const NOT_MEASURED = <span className="text-text-tertiary">—</span>;

export function AreaSummary({
  pair,
  a,
  b,
  detection,
}: {
  pair: ComparePair;
  a: SideTotals;
  b: SideTotals;
  detection: boolean;
}) {
  const coverageDelta =
    a.coverage && b.coverage ? formatPp((b.coverage.value - a.coverage.value) * 100) : "—";
  return (
    <PanelSection id="timeline-summary" index="01" title="Итог по району">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-line-hairline text-[11px] text-text-tertiary">
            <th scope="col" className="pb-1 text-left font-normal">
              <span className="sr-only">Показатель</span>
            </th>
            <th scope="col" className="px-1.5 pb-1 text-right font-mono font-medium">
              A · {dayMonth(pair.a.acquiredAt)}
            </th>
            <th scope="col" className="px-1.5 pb-1 text-right font-mono font-medium">
              B · {dayMonth(pair.b.acquiredAt)}
            </th>
            <th scope="col" className="pb-1 pl-1.5 text-right font-mono font-medium">
              Δ
            </th>
          </tr>
        </thead>
        <tbody>
          <SummaryRow
            label="Кандидатов"
            a={detection ? a.found : NOT_MEASURED}
            b={detection ? b.found : NOT_MEASURED}
            delta={detection ? formatSigned(b.found - a.found) : NOT_MEASURED}
          />
          <SummaryRow
            label="Площадь, км²"
            a={detection ? formatKm2(a.areaM2) : NOT_MEASURED}
            b={detection ? formatKm2(b.areaM2) : NOT_MEASURED}
            delta={detection ? formatSigned((b.areaM2 - a.areaM2) / 1_000_000, 2) : NOT_MEASURED}
          />
          <SummaryRow
            label="Среднее покрытие, %"
            a={<CoverageCell totals={a} />}
            b={<CoverageCell totals={b} />}
            delta={coverageDelta}
          />
          <SummaryRow
            label="Пригодная вода, %"
            a={formatNumber(a.validWater * 100)}
            b={formatNumber(b.validWater * 100)}
            delta={formatPp((b.validWater - a.validWater) * 100, 0)}
          />
        </tbody>
      </table>
      {!isUsable(pair.a) ? <IncompleteNote letter="A" scene={pair.a} totals={a} /> : null}
      {!isUsable(pair.b) ? <IncompleteNote letter="B" scene={pair.b} totals={b} /> : null}
      <p className="text-[11px] leading-4 text-text-tertiary">
        {detection
          ? "Покрытие — доля пикселя 10 м, среднее по найденным пятнам, под значением 90 % ДИ. Источник: фикстура demo/timeline · модель не подключена."
          : "Снимки A и B — из каталога Sentinel-2 L2A; пригодная вода — оценка по облачности тайла. Кандидаты, площадь и покрытие появятся с детектором."}
      </p>
    </PanelSection>
  );
}

function PassCell({ pass, scene }: { pass: CandidatePass | null; scene: SceneSummary }) {
  if (pass?.state === "found" && pass.coverage)
    return <span className="text-text-primary">{formatCoverage(pass.coverage.value)}</span>;
  if (pass?.state === "not-found")
    return (
      <span title="не найдено" className="text-text-tertiary">
        ○
      </span>
    );
  return (
    <span
      title={
        pass?.state === "cloudy"
          ? cloudText(scene)
          : `нет данных · облачность ${formatPercent(scene.cloudCover)}`
      }
      className="inline-block size-3 border border-dashed border-text-tertiary align-[-1px]"
    />
  );
}

const DELTA_WORD: Record<ObjectRow["kind"], string> = {
  change: "",
  new: "новое",
  gone: "исчезло",
  hidden: "—",
  absent: "—",
};

function passLabel(pass: CandidatePass | null, scene: SceneSummary): string {
  if (pass?.state === "found" && pass.coverage) return `${formatCoverage(pass.coverage.value)} %`;
  if (pass?.state === "not-found") return "не найдено";
  if (pass?.state === "cloudy") return cloudText(scene);
  return "нет данных";
}

function rowLabel(row: ObjectRow, pair: ComparePair): string {
  const delta =
    row.deltaPp !== null
      ? `изменение ${formatPp(row.deltaPp)}`
      : row.kind === "hidden"
        ? "сравнение невозможно"
        : DELTA_WORD[row.kind];
  return `${row.candidate.id}: покрытие A ${passLabel(row.a, pair.a)}, B ${passLabel(row.b, pair.b)}, ${delta}`;
}

const ROW_GRID = "grid grid-cols-[minmax(0,1fr)_3rem_3rem_3.75rem_4rem] items-center gap-x-1.5";

function ObjectDeltaRow({
  row,
  pair,
  selected,
}: {
  row: ObjectRow;
  pair: ComparePair;
  selected: boolean;
}) {
  const selectObject = useSelectObject();
  const setHint = useStatusHintStore((state) => state.setHint);
  return (
    <li>
      <button
        type="button"
        aria-label={rowLabel(row, pair)}
        aria-current={selected ? "true" : undefined}
        onClick={() => selectObject(row.candidate)}
        onMouseEnter={() => setHint(`${row.candidate.id} — щелчок: динамика пятна`)}
        onMouseLeave={() => setHint(null)}
        className={cn(
          ROW_GRID,
          "relative h-7 w-full px-1 text-left text-[12px] transition-colors duration-[var(--t-2)] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus-ring",
          selected
            ? "bg-accent-selection-wash shadow-[inset_3px_0_0_var(--accent-selection)]"
            : "hover:bg-surface-raised",
        )}
      >
        <span
          className={cn(
            "pl-1 font-mono font-medium whitespace-nowrap",
            selected ? "text-accent-selection" : "text-text-primary",
          )}
        >
          {row.candidate.id}
        </span>
        <span className="text-right font-mono">
          <PassCell pass={row.a} scene={pair.a} />
        </span>
        <span className="text-right font-mono">
          <PassCell pass={row.b} scene={pair.b} />
        </span>
        <span
          className={cn(
            "text-right font-mono whitespace-nowrap",
            row.deltaPp === null ? "text-text-tertiary" : "text-text-primary",
          )}
        >
          {row.deltaPp !== null ? formatSigned(row.deltaPp, 1) : DELTA_WORD[row.kind]}
        </span>
        <span className="flex justify-end pr-1">
          <DeltaBar deltaPp={row.deltaPp} />
        </span>
      </button>
    </li>
  );
}

export function ObjectDeltas({ rows, pair }: { rows: readonly ObjectRow[]; pair: ComparePair }) {
  const selectedId = useWorkspaceStore((state) => state.selectedCandidateId);
  const comparable = rows.filter((row) => row.deltaPp !== null).length;
  return (
    <PanelSection
      id="timeline-objects"
      index="02"
      title="По объектам"
      aside={
        <span className="text-[11px] text-text-tertiary">
          сравнимо {comparable} из {rows.length}
        </span>
      }
    >
      <div className={cn(ROW_GRID, "px-1 text-[11px] text-text-tertiary")} aria-hidden>
        <span className="pl-1">Объект</span>
        <span className="text-right">A, %</span>
        <span className="text-right">B, %</span>
        <span className="text-right">Δ, п.&nbsp;п.</span>
        <span />
      </div>
      <ul className="-mx-1 flex flex-col border-t border-line-hairline">
        {rows.map((row) => (
          <ObjectDeltaRow
            key={row.candidate.id}
            row={row}
            pair={pair}
            selected={row.candidate.id === selectedId}
          />
        ))}
      </ul>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-text-tertiary">
        <span className="inline-flex items-center gap-1.5">
          Δ покрытия <DeltaLegend />
        </span>
        <span>синий — убыль, жёлтый — рост</span>
        <span>○ не найдено · ⬚ облачно или нет данных</span>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <Checkbox
          checked={false}
          onChange={() => undefined}
          disabled
          disabledReason="Слой Δ покрытия появится с моделью доли покрытия пикселя"
          trailing={<PlannedTag capability="coverage_estimation" />}
        >
          Слой Δ на карте
        </Checkbox>
        <Button size="sm" disabled title="Кадры GIF A → B — экспорт появится с change_tracking">
          Кадры GIF
          <PlannedTag capability="change_tracking" />
        </Button>
      </div>
    </PanelSection>
  );
}
