"use client";

import { useCallback, useMemo, useState } from "react";
import { useCandidateObservations } from "@/data/monitor-passes";
import { type PlannedPass, usePlannedPasses } from "@/data/scenes";
import type { SceneSummary } from "@/domain/scene";
import { useQueue } from "@/features/shell/queue/use-queue";
import { formatPercent } from "@/lib/format/numbers";
import { formatUtcTime } from "@/lib/format/time";
import { Button } from "@/ui/button";
import { IconCaution } from "@/ui/icons";
import { PlannedTag } from "@/ui/planned";
import { PlannedControlBlock, SceneControlBlock } from "./rail-control-block";
import {
  AxisLane,
  Cursor,
  type EventMark,
  EventsLane,
  LANE_TOP,
  LANES,
  NowMarker,
  PassLane,
  type PassSignal,
  type PlannedMark,
  shortDay,
  SignalLane,
  type Tip,
  TrackFrame,
  TrackLabel,
  TrackTooltip,
  useLaneWidth,
  useZoomableWindow,
} from "./rail-tracks";
import { DAY, type TimeWindow, toRatio } from "./time-scale";
import { useNow } from "./use-now";
import { useScenePlayback } from "./use-scene-playback";
import { useSceneStepping } from "./use-scene-stepping";
import { useSelectedScene } from "./use-selected-scene";

const PAD_DAYS = 3;
const EMPTY_WINDOW_BEFORE_DAYS = 45;
const EMPTY_WINDOW_AFTER_DAYS = 15;

function fullWindow(
  scenes: readonly SceneSummary[],
  planned: readonly PlannedPass[],
  now: number,
): TimeWindow {
  if (!scenes.length)
    return {
      start: now - EMPTY_WINDOW_BEFORE_DAYS * DAY,
      end: now + EMPTY_WINDOW_AFTER_DAYS * DAY,
    };
  const times = scenes.map((scene) => Date.parse(scene.acquiredAt));
  const future = planned.map((pass) => Date.parse(pass.at));
  return {
    start: Math.min(...times) - PAD_DAYS * DAY,
    end: Math.max(now, ...times, ...future) + PAD_DAYS * DAY,
  };
}

function useSignals(scenes: readonly SceneSummary[]): Readonly<Record<string, PassSignal>> {
  const sourced = useCandidateObservations();
  const table = sourced.origin === "none" ? null : sourced.data;
  return useMemo(() => {
    const signals: Record<string, PassSignal> = {};
    if (!table) return signals;
    const all = Object.values(table);
    for (const scene of scenes) {
      if (scene.usability === "unusable") {
        signals[scene.id] = { areaM2: null, partial: true, found: 0 };
        continue;
      }
      let areaM2 = 0;
      let found = 0;
      let cloudy = false;
      for (const observations of all) {
        const observation = observations.find((entry) => entry.sceneId === scene.id);
        if (observation?.state === "found") {
          areaM2 += observation.areaM2 ?? 0;
          found += 1;
        }
        if (observation?.state === "cloudy") cloudy = true;
      }
      signals[scene.id] = { areaM2, partial: cloudy || scene.usability === "partial", found };
    }
    return signals;
  }, [scenes, table]);
}

function useEventMarks(): readonly EventMark[] {
  const { rows } = useQueue();
  return useMemo(
    () =>
      rows.flatMap((row) => {
        const state =
          row.state === "new" ? "НОВОЕ" : row.state === "acknowledged" ? "КВИТ." : "СВЕД.";
        const stamp = `${shortDay(row.occurredAt)}${row.stamp === "time" ? ` ${formatUtcTime(row.occurredAt)}` : ""}`;
        const marks: EventMark[] = [
          {
            id: row.id,
            at: row.occurredAt,
            severity: row.severity,
            acknowledged: row.state !== "new",
            operator: false,
            tooltip: `${stamp} · ${row.title} · ${state}${row.isDemo ? " · ДЕМО" : ""}`,
          },
        ];
        if (row.acknowledgement)
          marks.push({
            id: `${row.id}:ack`,
            at: row.acknowledgement.at,
            severity: "info",
            acknowledged: true,
            operator: true,
            tooltip: `${shortDay(row.acknowledgement.at)} ${formatUtcTime(row.acknowledgement.at)} · Квитировано · ${row.acknowledgement.actor}`,
          });
        return marks;
      }),
    [rows],
  );
}

function plannedMarks(planned: readonly PlannedPass[], now: number): PlannedMark[] {
  return planned
    .filter((pass) => Date.parse(pass.at) > now)
    .map((pass) => ({
      at: pass.at,
      label: `${shortDay(pass.at)} ${formatUtcTime(pass.at)} · ${pass.platform} · плановый пролёт`,
    }));
}

function CloudCallout({
  scene,
  window,
  width,
  nearest,
  onJump,
}: {
  scene: SceneSummary;
  window: TimeWindow;
  width: number;
  nearest: SceneSummary | null;
  onJump: () => void;
}) {
  const ratio = toRatio(window, Date.parse(scene.acquiredAt));
  if (scene.usability === "usable" || ratio < 0 || ratio > 1) return null;
  const onRight = ratio < 0.55;
  const x = ratio * width;
  const text =
    scene.usability === "unusable"
      ? `Снимок ${shortDay(scene.acquiredAt)}: облачность ${formatPercent(scene.cloudCover)} — объекты не наблюдались`
      : `Снимок ${shortDay(scene.acquiredAt)}: облачность ${formatPercent(scene.cloudCover)} — часть района не наблюдалась`;
  return (
    <div
      role="status"
      className="absolute z-10 flex max-w-[calc(100%-8px)] items-center gap-2 rounded-[var(--radius-ctl)] border border-line-control bg-surface-panel py-0.5 pr-1 pl-2 text-[12px] leading-4 text-text-primary shadow-popover"
      style={{
        top: LANE_TOP.signal + 2,
        ...(onRight ? { left: x + 10 } : { right: width - x + 10 }),
      }}
    >
      <IconCaution size={14} className="shrink-0 text-state-caution" />
      <span className="min-w-0">{text}</span>
      {nearest ? (
        <Button
          size="sm"
          onClick={onJump}
          title={`Ближайший пригодный — ${shortDay(nearest.acquiredAt)}`}
        >
          К ближайшему пригодному
        </Button>
      ) : null}
    </div>
  );
}

function PlannedTracks({ now }: { now: number }) {
  const { ref, width } = useLaneWidth();
  const window = useMemo(() => fullWindow([], [], now), [now]);
  const today = new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  })
    .format(now)
    .replace(" г.", "");
  return (
    <TrackFrame
      labels={
        <>
          <span />
          <TrackLabel>Пролёты S2</TrackLabel>
          <TrackLabel>Площадь, км²</TrackLabel>
          <TrackLabel>События</TrackLabel>
        </>
      }
      lanes={
        <div ref={ref} className="absolute inset-0">
          <AxisLane window={window} width={width} avoid={[now, now + 4 * DAY, now - 4 * DAY]} />
          <NowMarker
            window={window}
            now={now}
            label={`сегодня · ${today}`}
            futureLabel="плановые пролёты"
          />
          <div
            className="absolute inset-x-0 flex items-center gap-2 pr-4 text-[12px] text-text-tertiary"
            style={{ top: LANE_TOP.passes, height: LANES.passes }}
          >
            <span className="bg-surface-panel pr-2">
              Каталог снимков не подключён · scene_catalog: planned
            </span>
            <PlannedTag capability="scene_catalog" />
          </div>
          <div
            className="absolute inset-x-0 flex items-center text-[12px] text-text-tertiary"
            style={{ top: LANE_TOP.signal, height: LANES.signal }}
          >
            <span className="bg-surface-panel pr-2">
              Сигнал появится после подключения обнаружения
            </span>
          </div>
        </div>
      }
    />
  );
}

function SceneTracks({
  scenes,
  selected,
  isDemo,
  now,
  onSelect,
  nearest,
  onJumpNearest,
}: {
  scenes: readonly SceneSummary[];
  selected: SceneSummary;
  isDemo: boolean;
  now: number;
  onSelect: (id: string) => void;
  nearest: SceneSummary | null;
  onJumpNearest: () => void;
}) {
  const plannedSourced = usePlannedPasses();
  const planned = useMemo(
    () => (plannedSourced.origin === "none" ? [] : plannedSourced.data),
    [plannedSourced],
  );
  const { ref, width } = useLaneWidth();
  const [element, setElement] = useState<HTMLDivElement | null>(null);
  const bounds = useMemo(() => fullWindow(scenes, planned, now), [scenes, planned, now]);
  const { window, zoomed, reset } = useZoomableWindow(bounds, element);
  const signals = useSignals(scenes);
  const events = useEventMarks();
  const futurePasses = useMemo(() => plannedMarks(planned, now), [planned, now]);
  const [tip, setTip] = useState<Tip>(null);
  const nowAvoid = useMemo(() => [now], [now]);
  const setLanes = useCallback(
    (node: HTMLDivElement | null) => {
      ref.current = node;
      setElement(node);
    },
    [ref],
  );

  return (
    <TrackFrame
      labels={
        <>
          <span className="flex items-center">
            {zoomed ? (
              <button
                type="button"
                onClick={reset}
                className="font-mono text-[10.5px] leading-3 text-text-secondary underline underline-offset-2 hover:text-text-primary"
              >
                весь период
              </button>
            ) : null}
          </span>
          <TrackLabel demo={isDemo}>Пролёты S2</TrackLabel>
          <TrackLabel demo={isDemo}>Площадь, км²</TrackLabel>
          <TrackLabel demo={isDemo}>События</TrackLabel>
        </>
      }
      lanes={
        <div
          ref={setLanes}
          className="absolute inset-0"
          title="Колесо — масштаб шкалы · Shift + колесо — сдвиг"
          onDoubleClick={reset}
        >
          <AxisLane window={window} width={width} avoid={nowAvoid} />
          <NowMarker window={window} now={now} label="сейчас" futureLabel="плановые пролёты" />
          <SignalLane
            scenes={scenes}
            signals={signals}
            selectedId={selected.id}
            window={window}
            width={width}
            onTip={setTip}
          />
          <EventsLane events={events} window={window} width={width} onTip={setTip} />
          <Cursor window={window} at={Date.parse(selected.acquiredAt)} />
          <PassLane
            scenes={scenes}
            planned={futurePasses}
            selectedId={selected.id}
            window={window}
            width={width}
            onSelect={onSelect}
            onTip={setTip}
          />
          <CloudCallout
            scene={selected}
            window={window}
            width={width}
            nearest={nearest}
            onJump={onJumpNearest}
          />
          <TrackTooltip tip={tip} width={width} />
        </div>
      }
    />
  );
}

export function SceneRail() {
  const { scenes, isDemo } = useSelectedScene();
  const stepping = useSceneStepping(scenes);
  const now = useNow();
  const scene = stepping.current;
  const lastIndex = scenes.length - 1;
  const playback = useScenePlayback({
    enabled: scenes.length > 1,
    atEnd: stepping.currentIndex >= lastIndex,
    onStep: () => stepping.step(1),
    onRestart: () => {
      if (scenes[0]) stepping.select(scenes[0].id);
    },
  });

  return (
    <div className="grid h-full min-w-0 grid-cols-1 md:grid-cols-[var(--control-w)_minmax(0,1fr)]">
      {scene ? (
        <SceneControlBlock
          scene={scene}
          isDemo={isDemo}
          stepping={stepping}
          playback={playback}
          now={now}
        />
      ) : (
        <PlannedControlBlock />
      )}
      <div className="relative hidden min-w-0 md:block">
        {scene ? (
          <SceneTracks
            scenes={scenes}
            selected={scene}
            isDemo={isDemo}
            now={now}
            onSelect={stepping.select}
            nearest={stepping.nearestUsable}
            onJumpNearest={stepping.jumpToNearestUsable}
          />
        ) : (
          <PlannedTracks now={now} />
        )}
      </div>
    </div>
  );
}
