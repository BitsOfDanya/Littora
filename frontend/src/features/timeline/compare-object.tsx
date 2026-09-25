"use client";

import type { MouseEvent } from "react";
import type { CandidateHistory, CandidatePass } from "@/data/timeline";
import type { DebrisCandidate } from "@/domain/detection";
import type { SceneSummary } from "@/domain/scene";
import { ObservationSeries } from "@/features/inspector/parts/observation-series";
import { Readout, ReadoutGrid } from "@/features/inspector/parts/readout-grid";
import { formatNumber, formatSignedPercent } from "@/lib/format/numbers";
import { formatUtcTime } from "@/lib/format/time";
import { cn } from "@/ui/cn";
import { PanelSection } from "@/ui/section";
import {
  cloudText,
  formatCoverage,
  formatCoverageInterval,
  formatKm2,
  passStateText,
} from "./compare-format";
import {
  compassPoint,
  type ComparePair,
  type CompareSide,
  coverageSeries,
  dayMonth,
  isUsable,
  type ObjectDynamics,
  objectDynamics,
  passAt,
} from "./compare-model";
import { SideLetter } from "./compare-pickers";
import type { CompareActions } from "./use-compare";

function distanceValue(meters: number): string {
  return meters >= 1000
    ? formatNumber(meters / 1000, 1)
    : formatNumber(Math.round(meters / 10) * 10);
}

function sideValue(pass: CandidatePass | null, pick: (pass: CandidatePass) => string): string {
  if (pass?.state === "found") return pick(pass);
  if (pass?.state === "not-found") return "нет";
  return "—";
}

function sideReason(
  pass: CandidatePass | null,
  scene: SceneSummary,
  letter: "A" | "B",
): string | null {
  if (!pass || pass.state === "no-data") return `${letter}: нет данных`;
  if (pass.state === "cloudy") return `${letter}: ${cloudText(scene)}`;
  if (pass.state === "not-found") return `${letter}: не найдено`;
  return null;
}

function reasonOf(dynamics: ObjectDynamics, pair: ComparePair): string | null {
  return sideReason(dynamics.a, pair.a, "A") ?? sideReason(dynamics.b, pair.b, "B");
}

function DynamicsReadouts({ dynamics, pair }: { dynamics: ObjectDynamics; pair: ComparePair }) {
  const reason = reasonOf(dynamics, pair);
  const { a, b, displacement, persistence } = dynamics;
  const span = `${dayMonth(pair.a.acquiredAt)} → ${dayMonth(pair.b.acquiredAt)}`;
  const coverageInterval =
    a?.coverage && b?.coverage
      ? `90 % ДИ ${formatCoverageInterval(a.coverage)} → ${formatCoverageInterval(b.coverage)}`
      : reason;
  return (
    <ReadoutGrid>
      <Readout
        label="Площадь A → B"
        value={`${sideValue(a, (pass) => formatKm2(pass.areaM2 ?? 0))} → ${sideValue(b, (pass) => formatKm2(pass.areaM2 ?? 0))}`}
        unit="км²"
        interval={
          dynamics.areaRatio !== null ? `Δ ${formatSignedPercent(dynamics.areaRatio)}` : reason
        }
        note={span}
      />
      <Readout
        label="Смещение центра"
        value={displacement ? distanceValue(displacement.distanceM) : "—"}
        unit={displacement ? (displacement.distanceM >= 1000 ? "км" : "м") : undefined}
        interval={
          displacement
            ? `${compassPoint(displacement.bearingDeg)} ${formatNumber(displacement.bearingDeg)}°`
            : reason
        }
        note={displacement ? `центр контура A → B · ${span}` : "нужны оба наблюдения"}
      />
      <Readout
        label="Устойчивость"
        value={`${persistence.found} из ${persistence.usable}`}
        interval="пригодных пролётов"
        note={`до ${dayMonth(pair.aIndex > pair.bIndex ? pair.a.acquiredAt : pair.b.acquiredAt)} включительно`}
      />
      <Readout
        label="Покрытие A → B"
        value={`${sideValue(a, (pass) => formatCoverage(pass.coverage?.value ?? 0))} → ${sideValue(b, (pass) => formatCoverage(pass.coverage?.value ?? 0))}`}
        unit="%"
        interval={coverageInterval}
        note="доля пикселя 10 м"
      />
    </ReadoutGrid>
  );
}

function PassRow({
  scene,
  pass,
  side,
  onPick,
}: {
  scene: SceneSummary;
  pass: CandidatePass | undefined;
  side: CompareSide | null;
  onPick: (event: MouseEvent<HTMLButtonElement>) => void;
}) {
  const state = pass?.state ?? "no-data";
  return (
    <li>
      <button
        type="button"
        onClick={onPick}
        title="Щелчок — сделать датой B · Alt+щелчок — датой A"
        aria-label={`${dayMonth(scene.acquiredAt)} ${scene.platform}: ${passStateText(pass, scene)}${side ? `, дата ${side === "a" ? "A" : "B"}` : ""}`}
        className={cn(
          "grid h-[26px] w-full grid-cols-[1.25rem_3rem_3.25rem_2.5rem_minmax(0,1fr)] items-center gap-x-2 px-1 text-left text-[12px] hover:bg-surface-raised focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus-ring",
          side && "bg-surface-sunken",
        )}
      >
        {side ? <SideLetter side={side} className="size-4 text-[10.5px]" /> : <span />}
        <span className="font-mono text-text-primary">{dayMonth(scene.acquiredAt)}</span>
        <span className="font-mono text-text-tertiary">{formatUtcTime(scene.acquiredAt)}</span>
        <span className="font-mono text-text-secondary">{scene.platform}</span>
        <span
          className={cn(
            "whitespace-nowrap",
            state === "found" && "text-text-primary",
            state === "not-found" && "text-text-secondary",
            (state === "cloudy" || state === "no-data") && "text-text-tertiary",
          )}
        >
          {passStateText(pass, scene)}
        </span>
      </button>
    </li>
  );
}

export function ObjectDynamicsBody({
  candidate,
  history,
  scenes,
  pair,
  actions,
}: {
  candidate: DebrisCandidate;
  history: CandidateHistory | undefined;
  scenes: readonly SceneSummary[];
  pair: ComparePair;
  actions: CompareActions;
}) {
  const dynamics = objectDynamics(history, scenes, pair);
  const series = coverageSeries(history, scenes);
  const usable = scenes.filter(isUsable);
  const foundUsable = usable.filter((scene) => passAt(history, scene.id)?.state === "found").length;
  const sideOf = (scene: SceneSummary): CompareSide | null =>
    scene.id === pair.a.id ? "a" : scene.id === pair.b.id ? "b" : null;
  return (
    <>
      <PanelSection id="timeline-object-readouts" index="01" title="Динамика пятна">
        <DynamicsReadouts dynamics={dynamics} pair={pair} />
        <p className="text-[11px] leading-4 text-text-tertiary">
          Источник: фикстура demo/timeline · контуры A и B из истории наблюдений {candidate.id} ·
          модель не подключена.
        </p>
      </PanelSection>
      <PanelSection
        id="timeline-object-series"
        index="02"
        title="Покрытие по пролётам"
        aside={
          <span className="text-[11px] text-text-tertiary">
            найдено в {foundUsable} из {usable.length} пригодных
          </span>
        }
      >
        <ObservationSeries
          points={series}
          selectedId={pair.b.id}
          markers={[
            { id: pair.a.id, label: "A" },
            { id: pair.b.id, label: "B" },
          ]}
          unit="Покрытие, %"
          title={`Покрытие ${candidate.id} по пролётам с отметками дат A и B`}
        />
      </PanelSection>
      <PanelSection
        id="timeline-object-passes"
        index="03"
        title="Пролёты"
        aside={<span className="text-[11px] text-text-tertiary">Alt+щелчок — дата A</span>}
      >
        <ul className="-mx-1 flex flex-col">
          {[...scenes].reverse().map((scene) => (
            <PassRow
              key={scene.id}
              scene={scene}
              pass={passAt(history, scene.id)}
              side={sideOf(scene)}
              onPick={(event) => actions.setSide(event.altKey ? "a" : "b", scene.id)}
            />
          ))}
        </ul>
      </PanelSection>
    </>
  );
}
