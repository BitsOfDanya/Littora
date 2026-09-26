import type { DriftCoverageRow, DriftErrorRow, DriftMethodSummary } from "@/data/models";
import { cn } from "@/ui/cn";
import { formatNumber } from "@/lib/format/numbers";
import { StatusTag } from "@/ui/status-tag";
import { NARROW_NBSP } from "./format";
import { ReportSection } from "./report-section";

const FACT_LABEL = "text-[12px] leading-4 text-text-tertiary";
const FACT_VALUE = "text-[12px] leading-4 text-text-secondary";

const percent = (ratio: number) => {
  const value = ratio * 100;
  return formatNumber(value, Number.isInteger(value) ? 0 : 1);
};

function facts(drift: DriftMethodSummary): readonly [string, string][] {
  const stokes = drift.stokes.map((on) => (on ? "вкл" : "выкл")).join("/");
  return [
    ["Скорость", drift.velocity],
    ["Шаг", drift.integration],
    [
      "Ансамбль",
      `парусность ${drift.windages.map(percent).join(", ")}${NARROW_NBSP}% × стоксов дрейф ${stokes} × ${drift.particles} частиц = ${drift.members} на зону`,
    ],
    ["Диффузия", `${formatNumber(drift.diffusivityM2s)}${NARROW_NBSP}м²/с`],
    [
      "Горизонты",
      `${drift.horizonsH.join(", ")}${NARROW_NBSP}ч вперёд; назад до ${drift.maxHindcastHours}${NARROW_NBSP}ч`,
    ],
    ["Форсинг", drift.forcing.join("; ")],
    ...(drift.envelopeSpread ? ([["Облако", drift.envelopeSpread]] as [string, string][]) : []),
  ];
}

const CELL = "border-b border-line-hairline px-2 py-1 text-[12px] leading-4";
const HEAD =
  "border-b border-text-primary px-2 py-1 text-left text-[11px] font-semibold text-text-secondary";

function ErrorTable({ rows }: { rows: readonly DriftErrorRow[] }) {
  return (
    <div className="mt-5 flex flex-col gap-2">
      <p className="text-[12px] leading-4 text-text-secondary">
        Сверка с реальными треками: расстояние между медианой сценария и настоящей позицией, км.
        Сравнение — «стоит на месте» и «продолжает как двигался».
      </p>
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th className={HEAD}>Набор</th>
            <th className={HEAD}>Горизонт</th>
            <th className={cn(HEAD, "text-right")}>Окон</th>
            <th className={cn(HEAD, "text-right")}>Сценарий</th>
            <th className={cn(HEAD, "text-right")}>На месте</th>
            <th className={cn(HEAD, "text-right")}>Как двигался</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.label}-${row.horizonH}`} className="text-text-primary">
              <td className={CELL}>{row.label}</td>
              <td className={cn(CELL, "font-mono")}>{row.horizonH} ч</td>
              <td className={cn(CELL, "text-right font-mono")}>{row.windows}</td>
              <td className={cn(CELL, "text-right font-mono")}>{formatNumber(row.serviceKm, 1)}</td>
              <td className={cn(CELL, "text-right font-mono text-text-secondary")}>
                {formatNumber(row.stationaryKm, 1)}
              </td>
              <td className={cn(CELL, "text-right font-mono text-text-secondary")}>
                {formatNumber(row.persistenceKm, 1)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CoverageTable({
  rows,
  nominal,
}: {
  rows: readonly DriftCoverageRow[];
  nominal: number | null;
}) {
  return (
    <div className="mt-5 flex flex-col gap-2">
      <p className="text-[12px] leading-4 text-text-secondary">
        Доля реальных позиций внутри облака
        {nominal === null ? "" : ` ${percent(nominal)}${NARROW_NBSP}%`}: до калибровки разброса и
        после. Независимых случаев мало — это ориентир, не гарантия.
      </p>
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th className={HEAD}>Набор</th>
            <th className={HEAD}>Горизонт</th>
            <th className={cn(HEAD, "text-right")}>До</th>
            <th className={cn(HEAD, "text-right")}>После</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.label}-${row.horizonH}`} className="text-text-primary">
              <td className={CELL}>{row.label}</td>
              <td className={cn(CELL, "font-mono")}>{row.horizonH} ч</td>
              <td className={cn(CELL, "text-right font-mono text-text-secondary")}>
                {percent(row.before)}
                {NARROW_NBSP}%
              </td>
              <td className={cn(CELL, "text-right font-mono")}>
                {percent(row.after)}
                {NARROW_NBSP}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DriftSection({ drift, index }: { drift: DriftMethodSummary; index: number }) {
  return (
    <ReportSection id="drift" index={index}>
      <div className="grid grid-cols-12 gap-x-6 gap-y-4 border-t border-text-primary pt-3">
        <div className="col-span-12 flex flex-col gap-1.5 @3xl:col-span-4">
          <span className="font-mono text-[13px] leading-[18px] text-text-primary">
            {drift.model}
          </span>
          <StatusTag className="h-[18px] w-fit px-1.5 text-[11px]">{drift.label}</StatusTag>
          <p className="text-[12px] leading-4 text-text-secondary">{drift.reason}.</p>
        </div>
        <dl className="col-span-12 grid grid-cols-[88px_minmax(0,1fr)] gap-x-3 gap-y-1.5 @3xl:col-span-8">
          {facts(drift).map(([label, value]) => (
            <div key={label} className="contents">
              <dt className={FACT_LABEL}>{label}</dt>
              <dd className={FACT_VALUE}>{value}</dd>
            </div>
          ))}
        </dl>
      </div>
      {drift.errors.length ? <ErrorTable rows={drift.errors} /> : null}
      {drift.coverage.length ? (
        <CoverageTable rows={drift.coverage} nominal={drift.nominalCoverage} />
      ) : null}
    </ReportSection>
  );
}
