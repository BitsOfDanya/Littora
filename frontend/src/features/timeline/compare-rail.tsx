"use client";

import { useMemo, useState } from "react";
import type { SceneSummary } from "@/domain/scene";
import { formatPercent } from "@/lib/format/numbers";
import { formatUtcDate } from "@/lib/format/time";
import { useWorkspaceStore } from "@/state/workspace-store";
import { Button, IconButton } from "@/ui/button";
import { DemoTag } from "@/ui/demo-mark";
import { IconChevronLeft, IconChevronRight, IconPause, IconPlay } from "@/ui/icons";
import { SeverityGlyph } from "@/ui/indicators";
import { Caps } from "@/ui/section";
import {
  areaSeries,
  type ComparePair,
  coverageSeries,
  intervalOf,
  isUsable,
  MOSAIC_YEARS,
  railWindow,
} from "./compare-model";
import { SideLetter } from "./compare-pickers";
import { CompareTracks, EmptyTracks } from "./compare-tracks";
import { useCompareViewStore } from "./compare-view-store";
import { type CompareActions, useCompareActions, useCompareData } from "./use-compare";
import { useTogglePlayback } from "./use-playback";

function RailHeader({ isDemo }: { isDemo: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
      <Caps className="text-text-secondary">Сравнение дат</Caps>
      {isDemo ? <DemoTag /> : null}
      <span className="text-[12px] text-text-tertiary">A и B на шкале</span>
    </div>
  );
}

function DateChips({ pair }: { pair: ComparePair | null }) {
  const label = (side: "a" | "b", scene: SceneSummary | undefined) =>
    scene ? formatUtcDate(scene.acquiredAt) : `мозаика ${MOSAIC_YEARS[side]}`;
  return (
    <p className="flex items-center gap-1.5 font-mono text-[13px] font-semibold whitespace-nowrap text-text-primary">
      <SideLetter side="a" />
      <span>{label("a", pair?.a)}</span>
      <span aria-hidden className="font-sans font-normal text-text-tertiary">
        →
      </span>
      <span className="sr-only">к</span>
      <SideLetter side="b" />
      <span>{label("b", pair?.b)}</span>
    </p>
  );
}

function CautionLine({ pair }: { pair: ComparePair }) {
  const cloudy = !isUsable(pair.a) ? "A" : "B";
  const scene = cloudy === "A" ? pair.a : pair.b;
  return (
    <p className="flex items-start gap-1 text-[12px] leading-4 text-state-caution">
      <SeverityGlyph severity="caution" size={12} className="mt-0.5" />
      <span>
        {cloudy} облачно на {formatPercent(scene.cloudCover)} — сравнение неполное
      </span>
    </p>
  );
}

function PlayButton({ disabled, onToggle }: { disabled: boolean; onToggle: () => void }) {
  const playing = useCompareViewStore((state) => state.playing);
  return (
    <IconButton
      label={playing ? "Остановить перебор B" : "Перебрать B по пролётам"}
      shortcut="Space"
      size="sm"
      pressed={playing}
      disabled={disabled}
      onClick={onToggle}
    >
      {playing ? <IconPause /> : <IconPlay />}
    </IconButton>
  );
}

function StepButtons({ actions, disabled }: { actions: CompareActions; disabled: boolean }) {
  return (
    <>
      <IconButton
        label="B: предыдущий пролёт"
        shortcut="["
        size="sm"
        disabled={disabled || !actions.canStep("b", -1)}
        onClick={() => actions.step("b", -1)}
      >
        <IconChevronLeft />
      </IconButton>
      <IconButton
        label="B: следующий пролёт"
        shortcut="]"
        size="sm"
        disabled={disabled || !actions.canStep("b", 1)}
        onClick={() => actions.step("b", 1)}
      >
        <IconChevronRight />
      </IconButton>
    </>
  );
}

function ControlBlock() {
  const data = useCompareData();
  const { scenes, pair, isDemo, hasCatalog, enoughUsable } = data;
  const actions = useCompareActions(scenes, pair);
  const togglePlayback = useTogglePlayback(data, actions);
  const setDemoFixtures = useWorkspaceStore((state) => state.setDemoFixtures);
  const demoFixtures = useWorkspaceStore((state) => state.demoFixtures);
  const complete = pair ? isUsable(pair.a) && isUsable(pair.b) : true;
  const disabled = !pair || !enoughUsable;

  return (
    <div className="flex h-full w-[var(--control-w)] shrink-0 flex-col justify-center gap-1.5 border-r border-line-hairline px-4 py-2">
      <RailHeader isDemo={isDemo} />
      <DateChips pair={pair} />
      {!hasCatalog ? (
        <p className="text-[12px] leading-4 text-text-tertiary">
          Снимки дат появятся с каталогом Sentinel-2
        </p>
      ) : !pair ? null : complete ? (
        <p className="text-[12px] leading-4 text-text-secondary">
          B: {pair.b.platform} · облачность {formatPercent(pair.b.cloudCover)} · интервал{" "}
          {intervalOf(scenes, pair).days}&nbsp;сут
        </p>
      ) : (
        <CautionLine pair={pair} />
      )}
      <div className="flex flex-wrap items-center gap-1.5">
        {hasCatalog && pair && !complete && enoughUsable ? (
          <Button size="sm" onClick={actions.toNearestUsablePair}>
            К ближайшей пригодной паре
          </Button>
        ) : (
          <StepButtons actions={actions} disabled={disabled} />
        )}
        <PlayButton disabled={disabled} onToggle={togglePlayback} />
        {!hasCatalog && !demoFixtures ? (
          <Button
            size="sm"
            onClick={() => setDemoFixtures(true)}
            title="Включить демо-фикстуры · D"
          >
            Показать на демо-данных
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function Tracks() {
  const { scenes, histories, pair, isDemo, hasCatalog } = useCompareData();
  const actions = useCompareActions(scenes, pair);
  const selectedId = useWorkspaceStore((state) => state.selectedCandidateId);
  const [now] = useState(() => Date.now());
  const window = useMemo(() => railWindow(scenes, now), [scenes, now]);
  const history = histories.find((entry) => entry.candidateId === selectedId);
  const series = useMemo(
    () => (history ? coverageSeries(history, scenes) : areaSeries(histories, scenes)),
    [history, histories, scenes],
  );
  const seriesPoints = useMemo(
    () =>
      history
        ? series.map((point) => ({
            ...point,
            value: point.value === undefined ? undefined : point.value * 100,
            low: point.low === undefined ? undefined : point.low * 100,
            high: point.high === undefined ? undefined : point.high * 100,
          }))
        : series,
    [history, series],
  );

  if (!hasCatalog)
    return (
      <EmptyTracks
        window={window}
        now={now}
        message="Каталог снимков не подключён · scene_catalog: planned"
      />
    );
  return (
    <CompareTracks
      scenes={scenes}
      pair={pair}
      window={window}
      now={now}
      series={seriesPoints}
      seriesLabel={history ? `Покрытие ${history.candidateId}, %` : "Площадь по району, км²"}
      seriesUnit={history ? "%" : "км²"}
      isDemo={isDemo}
      onPick={actions.setSide}
    />
  );
}

export function CompareRail() {
  return (
    <div className="flex h-full min-h-0">
      <ControlBlock />
      <div className="hidden min-w-0 flex-1 md:block">
        <Tracks />
      </div>
    </div>
  );
}
