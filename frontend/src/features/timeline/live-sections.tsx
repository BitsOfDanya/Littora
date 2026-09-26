"use client";

import type { MouseEvent, ReactNode } from "react";
import { type LiveTimeline, useStartTimelineRun, useTimelineCompare } from "@/data/timeline";
import type { SceneSummary } from "@/domain/scene";
import { Readout, ReadoutGrid } from "@/features/inspector/parts/readout-grid";
import { countRu } from "@/features/shell/orientation/plural";
import { describeApiError } from "@/lib/api/errors";
import type { Timeline, TimelinePassAnalysis, TimelineRun } from "@/lib/api/timeline";
import { formatNumber, formatSigned } from "@/lib/format/numbers";
import { formatUtcTime } from "@/lib/format/time";
import { Button } from "@/ui/button";
import { cn } from "@/ui/cn";
import { SeverityGlyph } from "@/ui/indicators";
import { PanelSection } from "@/ui/section";
import { StatusTag, type StatusTone } from "@/ui/status-tag";
import { formatPp } from "./compare-format";
import { type ComparePair, type CompareSide, DAY_MS, dayMonth } from "./compare-model";
import { SideLetter } from "./compare-pickers";
import {
  analysisOf,
  type LivePasses,
  missingInPair,
  openUsable,
  type PassVerdict,
  passVerdict,
  runStateOf,
} from "./live-model";
import type { CompareActions } from "./use-compare";

const NBSP = " ";
const NUMBER_CELL = "px-1.5 py-1 text-right font-mono text-[13px] whitespace-nowrap";
const DASH = <span className="text-text-tertiary">—</span>;

const VERDICT_WORD: Record<PassVerdict, string> = {
  detected: "обнаружено",
  "not-detected": "не обнаружено",
  insufficient: "недостаточно данных",
  pending: "не анализирован",
};

const VERDICT_TONE: Record<PassVerdict, StatusTone> = {
  detected: "alarm",
  "not-detected": "ok",
  insufficient: "caution",
  pending: "neutral",
};

const RUN_WORD = {
  pending: "в очереди",
  running: "анализ…",
  done: "готово",
  cached: "сохранён",
  failed: "ошибка",
} as const;

function formatZoneArea(km2: number): string {
  if (km2 === 0) return "0";
  if (km2 < 0.01) return formatNumber(km2, 4);
  if (km2 < 1) return formatNumber(km2, 3);
  return formatNumber(km2, 2);
}

function signedArea(km2: number): string {
  return km2 === 0 ? "0" : `${km2 > 0 ? "+" : "−"}${formatZoneArea(Math.abs(km2))}`;
}

function zonesText(analysis: TimelinePassAnalysis): string {
  const count = analysis.zone_count ?? 0;
  const limited = analysis.zones_limited ? "≥" : "";
  return `${limited}${countRu(count, ["зона", "зоны", "зон"])}`;
}

function Row({
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
      <td className={cn(NUMBER_CELL, "text-text-primary")}>{a}</td>
      <td className={cn(NUMBER_CELL, "text-text-primary")}>{b}</td>
      <td className={cn(NUMBER_CELL, "pr-0 text-text-secondary")}>{delta}</td>
    </tr>
  );
}

function SideVerdict({
  side,
  scene,
  analysis,
}: {
  side: CompareSide;
  scene: SceneSummary;
  analysis: TimelinePassAnalysis | null;
}) {
  const verdict = passVerdict(analysis);
  return (
    <p className="flex min-w-0 items-center gap-1.5 text-[12px]">
      <SideLetter side={side} />
      <span className="font-mono text-text-primary">{dayMonth(scene.acquiredAt)}</span>
      <StatusTag tone={VERDICT_TONE[verdict]} title={analysis?.detection.reason}>
        {VERDICT_WORD[verdict]}
      </StatusTag>
      {analysis && verdict === "insufficient" ? (
        <span className="truncate text-[11px] text-text-tertiary" title={analysis.detection.reason}>
          {analysis.detection.reason}
        </span>
      ) : null}
    </p>
  );
}

function comparableBoth(a: TimelinePassAnalysis | null, b: TimelinePassAnalysis | null) {
  return (
    a?.zone_count !== null &&
    a?.zone_count !== undefined &&
    b?.zone_count !== null &&
    b?.zone_count !== undefined
  );
}

function concentrationValue(analysis: TimelinePassAnalysis | null): ReactNode {
  const value = analysis?.concentration.value ?? null;
  if (value === null) return DASH;
  return (
    <span title={analysis?.concentration.label}>{formatNumber(value, value >= 10 ? 0 : 2)}</span>
  );
}

function concentrationNote(
  a: TimelinePassAnalysis | null,
  b: TimelinePassAnalysis | null,
): string | null {
  const labels = [a, b].flatMap((analysis) => (analysis ? [analysis.concentration.label] : []));
  if (!labels.length) return null;
  const unique = [...new Set(labels)];
  return `Концентрация — ${unique.join(" / ")}: оценка модели по полевым профилям района, а не пересчёт найденных зон.`;
}

function StartButton({
  label,
  sceneIds,
  maxPasses,
  disabledReason,
  size = "sm",
}: {
  label: string;
  sceneIds?: readonly string[];
  maxPasses?: number;
  disabledReason: string | null;
  size?: "sm" | "md";
}) {
  const run = useStartTimelineRun();
  return (
    <div className="flex flex-col items-start gap-1">
      <Button
        size={size}
        variant="primary"
        busy={run.pending}
        disabled={Boolean(disabledReason) || run.pending}
        title={disabledReason ?? undefined}
        onClick={() => run.start({ sceneIds, maxPasses })}
      >
        {label}
      </Button>
      {run.error ? (
        <p className="flex items-start gap-1 text-[12px] leading-4 text-state-alarm">
          <SeverityGlyph severity="alarm" size={12} className="mt-0.5" />
          {run.error}
        </p>
      ) : null}
    </div>
  );
}

function runBlocker(timeline: Timeline): string | null {
  if (!timeline.models.detector) return "Детектор не подключён — анализировать нечем";
  if (timeline.run && (timeline.run.status === "queued" || timeline.run.status === "running"))
    return "Идёт анализ пролётов — дождитесь окончания";
  return null;
}

export function LiveSummary({
  pair,
  passes,
  timeline,
}: {
  pair: ComparePair;
  passes: LivePasses;
  timeline: Timeline;
}) {
  const a = analysisOf(passes, pair.a.id);
  const b = analysisOf(passes, pair.b.id);
  const both = comparableBoth(a, b);
  const missing = missingInPair(pair, passes);
  const concentration = concentrationNote(a, b);
  const zones = (analysis: TimelinePassAnalysis | null) =>
    analysis?.zone_count !== null && analysis?.zone_count !== undefined
      ? formatNumber(analysis.zone_count)
      : DASH;
  const area = (analysis: TimelinePassAnalysis | null) =>
    analysis?.area_km2 !== null && analysis?.area_km2 !== undefined
      ? formatZoneArea(analysis.area_km2)
      : DASH;
  const peak = (analysis: TimelinePassAnalysis | null) =>
    analysis?.probability_max !== null && analysis?.probability_max !== undefined
      ? formatNumber(analysis.probability_max, 2)
      : DASH;
  return (
    <PanelSection id="timeline-summary" index="01" title="Итог по району">
      <div className="flex flex-col gap-1">
        <SideVerdict side="a" scene={pair.a} analysis={a} />
        <SideVerdict side="b" scene={pair.b} analysis={b} />
      </div>
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
          <Row
            label="Зон выше порога"
            a={zones(a)}
            b={zones(b)}
            delta={both ? formatSigned((b?.zone_count ?? 0) - (a?.zone_count ?? 0)) : DASH}
          />
          <Row
            label="Площадь зон, км²"
            a={area(a)}
            b={area(b)}
            delta={both ? signedArea((b?.area_km2 ?? 0) - (a?.area_km2 ?? 0)) : DASH}
          />
          <Row label="Макс. вероятность" a={peak(a)} b={peak(b)} delta={DASH} />
          <Row
            label="Пригодная вода, %"
            a={formatNumber(pair.a.validWaterFraction * 100)}
            b={formatNumber(pair.b.validWaterFraction * 100)}
            delta={formatPp((pair.b.validWaterFraction - pair.a.validWaterFraction) * 100, 0)}
          />
          <Row
            label="Концентрация, шт./км²"
            a={concentrationValue(a)}
            b={concentrationValue(b)}
            delta={DASH}
          />
        </tbody>
      </table>
      {missing.length ? (
        <div className="flex flex-col items-start gap-1.5 border-t border-line-hairline pt-2">
          <p className="flex items-start gap-1.5 text-[12px] leading-4 text-state-caution">
            <SeverityGlyph severity="caution" size={12} className="mt-0.5" />
            <span>
              {missing.length === 2 ? "Даты A и B" : pair.a.id === missing[0] ? "Дата A" : "Дата B"}{" "}
              ещё не {missing.length === 2 ? "проанализированы" : "проанализирована"} — детекций по
              ним нет.
            </span>
          </p>
          <StartButton
            label={missing.length === 2 ? "Проанализировать A и B" : "Проанализировать дату"}
            sceneIds={missing}
            disabledReason={runBlocker(timeline)}
          />
        </div>
      ) : null}
      <p className="text-[11px] leading-4 text-text-tertiary">
        {timeline.note} Зоны — связные области выше порога детектора на снимке.
        {concentration ? ` ${concentration}` : ""}
      </p>
    </PanelSection>
  );
}

function ChangeBody({ pair, passes }: { pair: ComparePair; passes: LivePasses }) {
  const a = analysisOf(passes, pair.a.id);
  const b = analysisOf(passes, pair.b.id);
  const forward = Date.parse(pair.a.acquiredAt) <= Date.parse(pair.b.acquiredAt);
  const before = forward ? a : b;
  const after = forward ? b : a;
  const compare = useTimelineCompare(before?.id ?? null, after?.id ?? null);
  if (!a || !b)
    return (
      <p className="text-[12px] leading-4 text-text-secondary">
        Изменения считаются, когда проанализированы обе даты.
      </p>
    );
  if (compare.isPending)
    return <p className="text-[12px] leading-4 text-text-tertiary">Сопоставляем зоны A и B…</p>;
  if (compare.isError)
    return (
      <p className="flex flex-wrap items-center gap-2 text-[12px] leading-4 text-state-alarm">
        Не удалось сопоставить: {describeApiError(compare.error)}
        <Button size="sm" onClick={() => void compare.refetch()}>
          Повторить
        </Button>
      </p>
    );
  const data = compare.data;
  if (!data.comparable || !data.counts || !data.area_km2)
    return (
      <p className="flex items-start gap-1.5 text-[12px] leading-4 text-state-caution">
        <SeverityGlyph severity="caution" size={12} className="mt-0.5" />
        <span>Сравнение невозможно: {data.reason ?? "нет данных"}.</span>
      </p>
    );
  const { counts, area_km2: areas } = data;
  const early = forward ? "A" : "B";
  const late = forward ? "B" : "A";
  return (
    <>
      <ReadoutGrid>
        <Readout
          label="Новые зоны"
          value={formatNumber(counts.new)}
          interval={`${formatZoneArea(areas.new)}${NBSP}км²`}
          note={`есть на ${late}, нет на ${early}`}
        />
        <Readout
          label="На том же месте"
          value={formatNumber(counts.persisting)}
          interval={`${formatZoneArea(areas.persisting)}${NBSP}км² на ${late}`}
          note="контуры перекрываются"
        />
        <Readout
          label="Исчезли"
          value={formatNumber(counts.disappeared)}
          interval={`${formatZoneArea(areas.disappeared)}${NBSP}км² на ${early}`}
          note={`были на ${early}, нет на ${late}`}
        />
        {data.masks_checked ? (
          <Readout
            label="Не наблюдались"
            value={formatNumber(counts.not_observed)}
            interval={`${formatZoneArea(areas.not_observed)}${NBSP}км²`}
            note="облака / вне снимка на другой дате"
          />
        ) : (
          <Readout
            label="Не наблюдались"
            value={DASH}
            note="нет маски облаков — не отделены от исчезнувших и новых"
          />
        )}
        <Readout
          className="col-span-2"
          label="Интервал"
          value={formatNumber(
            Math.round(
              Math.abs(Date.parse(pair.b.acquiredAt) - Date.parse(pair.a.acquiredAt)) / DAY_MS,
            ),
          )}
          unit="сут"
          note={`${dayMonth(pair.a.acquiredAt)} → ${dayMonth(pair.b.acquiredAt)}`}
        />
      </ReadoutGrid>
      {data.method ? (
        <p className="text-[11px] leading-4 text-text-tertiary">Метод: {data.method}.</p>
      ) : null}
    </>
  );
}

export function LiveChange({ pair, passes }: { pair: ComparePair; passes: LivePasses }) {
  return (
    <PanelSection id="timeline-change" index="02" title="Изменения A → B">
      <ChangeBody pair={pair} passes={passes} />
    </PanelSection>
  );
}

function runLine(run: TimelineRun, scenes: readonly SceneSummary[]): string {
  const current = scenes.find((scene) => scene.id === run.current_scene_id);
  const at = current ? ` · сейчас ${dayMonth(current.acquiredAt)} ${current.platform}` : "";
  return `Анализ пролётов: ${run.completed} из ${run.total}${at}`;
}

function RunStatus({ run, scenes }: { run: TimelineRun | null; scenes: readonly SceneSummary[] }) {
  if (!run) return null;
  const active = run.status === "queued" || run.status === "running";
  if (active)
    return (
      <div className="flex flex-col gap-1">
        <p className="text-[12px] leading-4 text-text-secondary">{runLine(run, scenes)}</p>
        <div
          role="progressbar"
          aria-label="Анализ пролётов"
          aria-valuemin={0}
          aria-valuemax={run.total}
          aria-valuenow={run.completed}
          className="h-1 w-full bg-surface-sunken"
        >
          <div
            className="h-full bg-text-secondary transition-[width] duration-[var(--t-2)]"
            style={{ width: `${run.total ? (run.completed / run.total) * 100 : 0}%` }}
          />
        </div>
        <p className="text-[11px] leading-4 text-text-tertiary">
          Каждый пролёт — полный анализ снимка по всем каналам, это минуты. Результаты сохраняются и
          появляются в ряду по мере готовности.
        </p>
      </div>
    );
  if (run.message)
    return (
      <p
        className={cn(
          "flex items-start gap-1.5 text-[12px] leading-4",
          run.failed ? "text-state-caution" : "text-text-tertiary",
        )}
      >
        {run.failed ? <SeverityGlyph severity="caution" size={12} className="mt-0.5" /> : null}
        <span>{run.message}</span>
      </p>
    );
  return null;
}

function passLine(
  analysis: TimelinePassAnalysis | null,
  runState: ReturnType<typeof runStateOf>,
): string {
  if (!analysis) return runState && runState !== "done" ? RUN_WORD[runState] : "не анализирован";
  const verdict = passVerdict(analysis);
  if (verdict === "insufficient") return VERDICT_WORD.insufficient;
  if (verdict === "not-detected") return "зон нет";
  return `${zonesText(analysis)} · ${formatZoneArea(analysis.area_km2 ?? 0)}${NBSP}км²`;
}

function changeLine(change: Timeline["passes"][number]["change"]): string | null {
  if (!change) return null;
  const { counts } = change;
  const parts = [];
  if (counts.new) parts.push(`+${counts.new} нов.`);
  if (counts.persisting) parts.push(`${counts.persisting} на месте`);
  if (counts.disappeared) parts.push(`−${counts.disappeared} исч.`);
  if (counts.not_observed) parts.push(`${counts.not_observed} не набл.`);
  return parts.length ? parts.join(" · ") : "без изменений";
}

function LivePassRow({
  scene,
  timeline,
  passes,
  side,
  onPick,
}: {
  scene: SceneSummary;
  timeline: Timeline;
  passes: LivePasses;
  side: CompareSide | null;
  onPick: (event: MouseEvent<HTMLButtonElement>) => void;
}) {
  const pass = passes.get(scene.id);
  const analysis = pass?.analysis ?? null;
  const verdict = passVerdict(analysis);
  const runState = runStateOf(timeline.run, scene.id);
  const line = passLine(analysis, runState);
  const change = changeLine(pass?.change ?? null);
  return (
    <li>
      <button
        type="button"
        onClick={onPick}
        title={`${analysis?.detection.reason ?? line} · щелчок — дата B, Alt+щелчок — дата A`}
        aria-label={`${dayMonth(scene.acquiredAt)} ${scene.platform}: ${line}${change ? `, ${change}` : ""}${side ? `, дата ${side === "a" ? "A" : "B"}` : ""}`}
        className={cn(
          "grid min-h-[26px] w-full grid-cols-[1.25rem_3rem_3.25rem_2.5rem_minmax(0,1fr)] items-center gap-x-2 px-1 py-0.5 text-left text-[12px] hover:bg-surface-raised focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus-ring",
          side && "bg-surface-sunken",
        )}
      >
        {side ? <SideLetter side={side} className="size-4 text-[10.5px]" /> : <span />}
        <span className="font-mono text-text-primary">{dayMonth(scene.acquiredAt)}</span>
        <span className="font-mono text-text-tertiary">{formatUtcTime(scene.acquiredAt)}</span>
        <span className="font-mono text-text-secondary">{scene.platform}</span>
        <span className="flex min-w-0 flex-col leading-4">
          <span
            className={cn(
              "truncate",
              verdict === "detected" && "text-text-primary",
              verdict === "not-detected" && "text-text-secondary",
              (verdict === "insufficient" || verdict === "pending") && "text-text-tertiary",
              runState === "running" && "text-text-primary",
              runState === "failed" && !analysis && "text-state-alarm",
            )}
          >
            {line}
          </span>
          {change ? (
            <span className="truncate font-mono text-[11px] text-text-tertiary">{change}</span>
          ) : null}
        </span>
      </button>
    </li>
  );
}

export function LivePassList({
  scenes,
  pair,
  passes,
  timeline,
  actions,
}: {
  scenes: readonly SceneSummary[];
  pair: ComparePair;
  passes: LivePasses;
  timeline: Timeline;
  actions: CompareActions;
}) {
  const open = openUsable(scenes, passes);
  const batch = Math.min(timeline.limits.default_passes, open);
  const blocker =
    runBlocker(timeline) ??
    (open === 0 ? "Все пригодные пролёты периода уже проанализированы" : null);
  const sideOf = (scene: SceneSummary): CompareSide | null =>
    scene.id === pair.a.id ? "a" : scene.id === pair.b.id ? "b" : null;
  return (
    <PanelSection
      id="timeline-passes"
      index="03"
      title="Пролёты периода"
      aside={
        <span className="text-[11px] text-text-tertiary">
          проанализировано {timeline.summary.analysed} из {timeline.summary.passes}
        </span>
      }
    >
      <RunStatus run={timeline.run} scenes={scenes} />
      <StartButton
        label={
          batch
            ? `Проанализировать ${countRu(batch, ["пролёт", "пролёта", "пролётов"])}`
            : "Проанализировать пролёты"
        }
        maxPasses={timeline.limits.default_passes}
        disabledReason={blocker}
      />
      <p className="text-[11px] leading-4 text-text-tertiary">
        Берутся пригодные пролёты без анализа, равномерно по периоду; сохранённые анализы этого
        района с текущими моделями используются повторно.
      </p>
      <ul className="-mx-1 flex flex-col border-t border-line-hairline">
        {[...scenes].reverse().map((scene) => (
          <LivePassRow
            key={scene.id}
            scene={scene}
            timeline={timeline}
            passes={passes}
            side={sideOf(scene)}
            onPick={(event) => actions.setSide(event.altKey ? "a" : "b", scene.id)}
          />
        ))}
      </ul>
    </PanelSection>
  );
}

export function LiveState({ live }: { live: LiveTimeline }) {
  if (live.status === "loading")
    return (
      <PanelSection index="01" title="Итог по району">
        <p className="text-[12px] leading-4 text-text-tertiary">Загружаем ряд детекций…</p>
      </PanelSection>
    );
  if (live.status === "error")
    return (
      <PanelSection index="01" title="Итог по району">
        <p className="flex flex-wrap items-center gap-2 text-[12px] leading-4 text-state-alarm">
          Ряд детекций не загружен: {live.message}
          <Button size="sm" onClick={live.retry}>
            Повторить
          </Button>
        </p>
      </PanelSection>
    );
  return null;
}
