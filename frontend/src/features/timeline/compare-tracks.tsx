"use client";

import {
  type KeyboardEvent,
  type MouseEvent,
  type RefObject,
  useEffect,
  useRef,
  useState,
} from "react";
import type { SceneSummary } from "@/domain/scene";
import type { SeriesPoint } from "@/features/inspector/parts/observation-series";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { formatNumber, formatPercent } from "@/lib/format/numbers";
import { formatLongDate, formatUtcDateTime, monthShortName } from "@/lib/format/time";
import { cn } from "@/ui/cn";
import { DemoTag } from "@/ui/demo-mark";
import {
  type ComparePair,
  type CompareSide,
  DAY_MS,
  ratioIn,
  type TimeWindow,
} from "./compare-model";

export const RAIL_B_PASS_ID = "timeline-rail-pass-b";

const LABEL_W = 112;
const MONTH_LEAD_ROOM = 0.08;
const USABILITY_WORD = {
  usable: "пригоден",
  partial: "частично облачно",
  unusable: "непригоден",
} as const;

type Size = { width: number; height: number };

function useElementSize(ref: RefObject<HTMLElement | null>): Size {
  const [size, setSize] = useState<Size>({ width: 0, height: 0 });
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) =>
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height }),
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return size;
}

function leftOf(window: TimeWindow, time: string | number): string {
  const value = typeof time === "number" ? time : Date.parse(time);
  return `${ratioIn(window, value) * 100}%`;
}

function sideWord(side: CompareSide | null): string {
  return side ? `, дата ${side === "a" ? "A" : "B"}` : "";
}

function passTitle(scene: SceneSummary): string {
  return `${formatUtcDateTime(scene.acquiredAt)} · ${scene.platform} · облачность ${formatPercent(scene.cloudCover)} · ${USABILITY_WORD[scene.usability]}`;
}

function monthStarts(window: TimeWindow): number[] {
  const starts: number[] = [];
  const cursor = new Date(window.start);
  cursor.setUTCDate(1);
  cursor.setUTCHours(0, 0, 0, 0);
  const first = cursor.getTime();
  while (cursor.getTime() <= window.end) {
    if (cursor.getTime() >= window.start) starts.push(cursor.getTime());
    cursor.setUTCMonth(cursor.getUTCMonth() + 1);
  }
  const firstShown = starts[0];
  const leadRoom = firstShown === undefined ? 1 : ratioIn(window, firstShown);
  return first < window.start && leadRoom > MONTH_LEAD_ROOM ? [window.start, ...starts] : starts;
}

function dayTicks(window: TimeWindow): number[] {
  const ticks: number[] = [];
  for (let time = Math.ceil(window.start / DAY_MS) * DAY_MS; time <= window.end; time += DAY_MS) {
    const day = new Date(time).getUTCDate();
    if (day % 5 === 0 && day < 30) ticks.push(time);
  }
  return ticks;
}

function Axis({ window }: { window: TimeWindow }) {
  return (
    <div className="relative h-full border-b border-line-control">
      {monthStarts(window).map((time) => {
        const date = new Date(time);
        return (
          <span
            key={time}
            className={cn(
              "absolute top-0 h-full pl-1 text-[11px] leading-[14px] font-semibold whitespace-nowrap text-text-secondary",
              time > window.start && "border-l border-line-control",
            )}
            style={{ left: leftOf(window, time) }}
          >
            {monthShortName(date.getUTCMonth())} {date.getUTCFullYear()}
          </span>
        );
      })}
      {dayTicks(window).map((time) => (
        <span
          key={time}
          aria-hidden
          className="absolute bottom-0 h-1 border-l border-text-tertiary"
          style={{ left: leftOf(window, time) }}
        >
          <span className="absolute bottom-1 -translate-x-1/2 font-mono text-[10.5px] leading-3 text-text-tertiary">
            {new Date(time).getUTCDate()}
          </span>
        </span>
      ))}
    </div>
  );
}

type PassMarkProps = {
  scene: SceneSummary;
  side: CompareSide | null;
  focusable: boolean;
  window: TimeWindow;
  onPick: (side: CompareSide) => void;
  onFocusMark: () => void;
  onKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => void;
  registerRef: (element: HTMLButtonElement | null) => void;
};

function PassMark({
  scene,
  side,
  focusable,
  window,
  onPick,
  onFocusMark,
  onKeyDown,
  registerRef,
}: PassMarkProps) {
  const setHint = useStatusHintStore((state) => state.setHint);
  const title = `${passTitle(scene)}${side ? ` · дата ${side === "a" ? "A" : "B"}` : ""}`;
  return (
    <button
      ref={registerRef}
      id={side === "b" ? RAIL_B_PASS_ID : undefined}
      type="button"
      tabIndex={focusable ? 0 : -1}
      aria-label={`${formatLongDate(scene.acquiredAt)}, ${scene.platform}, облачность ${formatPercent(scene.cloudCover)}, ${USABILITY_WORD[scene.usability]}${sideWord(side)}`}
      aria-pressed={side !== null}
      title={`${title} · щелчок — дата B, Alt+щелчок — дата A`}
      onClick={(event: MouseEvent<HTMLButtonElement>) => onPick(event.altKey ? "a" : "b")}
      onFocus={onFocusMark}
      onKeyDown={onKeyDown}
      onMouseEnter={() => setHint(`${title} — щелчок: дата B · Alt+щелчок: дата A`)}
      onMouseLeave={() => setHint(null)}
      className="group absolute top-0 z-[1] flex h-full w-[14px] -translate-x-1/2 flex-col items-center justify-end pb-1.5 focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-focus-ring"
      style={{ left: leftOf(window, scene.acquiredAt) }}
    >
      {scene.usability === "partial" ? (
        <span className="font-mono text-[10.5px] leading-3 text-text-tertiary">
          {Math.round(scene.cloudCover * 100)}
        </span>
      ) : null}
      <span
        aria-hidden
        className={cn(
          "mt-px block size-2.5 border group-hover:outline group-hover:outline-1 group-hover:outline-offset-2 group-hover:outline-text-secondary",
          scene.usability === "usable" && "border-text-primary bg-text-primary",
          scene.usability === "partial" && "border-text-primary bg-surface-panel",
          scene.usability === "unusable" &&
            "border-text-tertiary bg-[repeating-linear-gradient(45deg,var(--text-tertiary)_0_1px,transparent_1px_3px)]",
        )}
      />
    </button>
  );
}

function splitRuns(points: readonly SeriesPoint[]): SeriesPoint[][] {
  const runs: SeriesPoint[][] = [];
  let run: SeriesPoint[] = [];
  for (const point of points) {
    if (point.state === "observed" && point.value !== undefined) run.push(point);
    else if (point.state === "cloudy" || point.state === "no-data") {
      if (run.length) runs.push(run);
      run = [];
    }
  }
  if (run.length) runs.push(run);
  return runs;
}

function SeriesSvg({
  points,
  window,
  size,
  unit,
}: {
  points: readonly SeriesPoint[];
  window: TimeWindow;
  size: Size;
  unit: string;
}) {
  const top = 12;
  const bottom = size.height - 5;
  const max = Math.max(1e-6, ...points.map((point) => point.high ?? point.value ?? 0)) * 1.1;
  const x = (iso: string) => ratioIn(window, Date.parse(iso)) * size.width;
  const y = (value: number) => bottom - (value / max) * (bottom - top);
  return (
    <svg
      width={size.width}
      height={size.height}
      aria-hidden
      className="absolute inset-0 overflow-visible"
    >
      <line
        x1={0}
        x2={size.width}
        y1={y(max / 1.1)}
        y2={y(max / 1.1)}
        stroke="var(--line-hairline)"
        strokeDasharray="2 3"
      />
      <text x={3} y={y(max / 1.1) - 3} className="fill-text-tertiary font-mono text-[10.5px]">
        {formatNumber(max / 1.1, max < 1 ? 2 : 0)} {unit}
      </text>
      {splitRuns(points).map((run) => (
        <polyline
          key={run[0].id}
          fill="none"
          stroke="var(--text-primary)"
          strokeWidth={1.4}
          points={run.map((point) => `${x(point.time)},${y(point.value ?? 0)}`).join(" ")}
        />
      ))}
      {points.map((point) => {
        const cx = x(point.time);
        if (point.state === "observed" && point.value !== undefined)
          return (
            <g key={point.id}>
              {point.low !== undefined && point.high !== undefined ? (
                <line
                  x1={cx}
                  x2={cx}
                  y1={y(point.low)}
                  y2={y(point.high)}
                  stroke="var(--text-secondary)"
                />
              ) : null}
              <rect
                x={cx - 2.5}
                y={y(point.value) - 2.5}
                width={5}
                height={5}
                fill="var(--text-primary)"
              />
            </g>
          );
        if (point.state === "not-found")
          return (
            <circle
              key={point.id}
              cx={cx}
              cy={bottom - 3}
              r={2.5}
              fill="none"
              stroke="var(--text-secondary)"
            />
          );
        return (
          <rect
            key={point.id}
            x={cx - 3.5}
            y={bottom - 8}
            width={7}
            height={7}
            fill="none"
            stroke="var(--text-tertiary)"
            strokeDasharray="1.5 1.5"
          />
        );
      })}
    </svg>
  );
}

function SeriesPlot({
  points,
  window,
  unit,
}: {
  points: readonly SeriesPoint[];
  window: TimeWindow;
  unit: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const size = useElementSize(ref);
  return (
    <div ref={ref} className="relative h-full min-h-0">
      {size.width > 0 && size.height > 0 ? (
        <SeriesSvg points={points} window={window} size={size} unit={unit} />
      ) : null}
    </div>
  );
}

function Flag({
  side,
  scene,
  window,
}: {
  side: CompareSide;
  scene: SceneSummary;
  window: TimeWindow;
}) {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-y-0 w-0"
      style={{ left: leftOf(window, scene.acquiredAt) }}
    >
      <span className="absolute top-4 bottom-0 -left-[0.75px] w-[1.5px] bg-text-primary" />
      <span className="absolute top-0 -left-[9px] grid h-4 w-[18px] place-items-center bg-primary-fill font-sans text-[11px] font-bold text-primary-text">
        {side === "a" ? "A" : "B"}
      </span>
    </div>
  );
}

function usePassFocus(scenes: readonly SceneSummary[], pair: ComparePair | null) {
  const refs = useRef(new Map<string, HTMLButtonElement>());
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const activeId =
    focusedId && scenes.some((scene) => scene.id === focusedId)
      ? focusedId
      : (pair?.b.id ?? scenes.at(-1)?.id ?? null);
  const move = (index: number) => {
    const scene = scenes[Math.max(0, Math.min(scenes.length - 1, index))];
    if (!scene) return;
    setFocusedId(scene.id);
    refs.current.get(scene.id)?.focus();
  };
  return { refs, activeId, setFocusedId, move };
}

export type CompareTracksProps = {
  scenes: readonly SceneSummary[];
  pair: ComparePair | null;
  window: TimeWindow;
  now: number;
  series: readonly SeriesPoint[];
  seriesLabel: string;
  seriesUnit: string;
  isDemo: boolean;
  onPick: (side: CompareSide, sceneId: string) => void;
};

const GRID_ROWS = "grid-rows-[18px_30px_minmax(0,1fr)]";

export function CompareTracks({
  scenes,
  pair,
  window,
  now,
  series,
  seriesLabel,
  seriesUnit,
  isDemo,
  onPick,
}: CompareTracksProps) {
  const focus = usePassFocus(scenes, pair);
  const sideOf = (scene: SceneSummary): CompareSide | null =>
    pair?.a.id === scene.id ? "a" : pair?.b.id === scene.id ? "b" : null;
  const from = pair ? Math.min(Date.parse(pair.a.acquiredAt), Date.parse(pair.b.acquiredAt)) : 0;
  const to = pair ? Math.max(Date.parse(pair.a.acquiredAt), Date.parse(pair.b.acquiredAt)) : 0;
  const showNow = now <= window.end;

  const handleKeyDown =
    (index: number, scene: SceneSummary) => (event: KeyboardEvent<HTMLButtonElement>) => {
      const moves: Record<string, number> = {
        ArrowLeft: index - 1,
        ArrowRight: index + 1,
        Home: 0,
        End: scenes.length - 1,
      };
      if (event.key in moves) {
        event.preventDefault();
        event.stopPropagation();
        focus.move(moves[event.key]);
      } else if (event.key === "Enter") {
        event.preventDefault();
        event.stopPropagation();
        onPick(event.altKey ? "a" : "b", scene.id);
      }
    };

  return (
    <div
      className={cn("relative grid h-full min-w-0 py-2 pr-4", GRID_ROWS)}
      style={{ gridTemplateColumns: `${LABEL_W}px minmax(0,1fr)` }}
    >
      <div aria-hidden className="pointer-events-none relative col-start-2 row-span-3 row-start-1">
        {pair ? (
          <span
            className="absolute top-[18px] bottom-0 bg-accent-selection-wash"
            style={{
              left: leftOf(window, from),
              width: `${(ratioIn(window, to) - ratioIn(window, from)) * 100}%`,
            }}
          />
        ) : null}
        {showNow ? (
          <span
            className="absolute top-[18px] right-0 bottom-0 bg-[repeating-linear-gradient(45deg,var(--line-hairline)_0_1px,transparent_1px_6px)]"
            style={{ left: leftOf(window, now) }}
          />
        ) : null}
      </div>
      <span className="col-start-1 row-start-1" />
      <div className="relative col-start-2 row-start-1">
        <Axis window={window} />
      </div>
      <span className="col-start-1 row-start-2 flex items-center pl-4 text-[11px] leading-[13px] text-text-secondary">
        Пролёты S2
      </span>
      <div
        role="group"
        aria-label="Пролёты Sentinel-2: стрелки — выбор пролёта, Enter — дата B, Alt+Enter — дата A"
        className="relative col-start-2 row-start-2"
      >
        {scenes.map((scene, index) => (
          <PassMark
            key={scene.id}
            scene={scene}
            side={sideOf(scene)}
            focusable={scene.id === focus.activeId}
            window={window}
            onPick={(side) => onPick(side, scene.id)}
            onFocusMark={() => focus.setFocusedId(scene.id)}
            onKeyDown={handleKeyDown(index, scene)}
            registerRef={(element) => {
              if (element) focus.refs.current.set(scene.id, element);
              else focus.refs.current.delete(scene.id);
            }}
          />
        ))}
      </div>
      <span className="col-start-1 row-start-3 flex flex-col items-start gap-1 pt-1 pl-4 text-[11px] leading-[13px] text-text-secondary">
        <span>{seriesLabel}</span>
        {isDemo ? <DemoTag /> : null}
      </span>
      <div className="relative col-start-2 row-start-3 min-h-0 border-b border-line-hairline">
        <SeriesPlot points={series} window={window} unit={seriesUnit} />
      </div>
      <div aria-hidden className="pointer-events-none relative col-start-2 row-span-3 row-start-1">
        {showNow ? (
          <span
            className="absolute top-[18px] bottom-0 border-l border-dashed border-text-secondary"
            style={{ left: leftOf(window, now) }}
          >
            <span className="absolute bottom-0.5 left-1 text-[11px] leading-3 text-text-secondary">
              сейчас
            </span>
          </span>
        ) : null}
        {pair ? (
          <>
            <Flag side="a" scene={pair.a} window={window} />
            <Flag side="b" scene={pair.b} window={window} />
          </>
        ) : null}
      </div>
    </div>
  );
}

export function EmptyTracks({
  window,
  now,
  message,
}: {
  window: TimeWindow;
  now: number;
  message: string;
}) {
  return (
    <div
      className={cn("relative grid h-full min-w-0 py-2 pr-4", GRID_ROWS)}
      style={{ gridTemplateColumns: `${LABEL_W}px minmax(0,1fr)` }}
    >
      <span />
      <div className="relative">
        <Axis window={window} />
        <span
          className="absolute top-[18px] h-[80px] border-l border-dashed border-text-secondary"
          style={{ left: leftOf(window, now) }}
        >
          <span className="absolute top-1 left-1 text-[11px] leading-3 whitespace-nowrap text-text-secondary">
            сейчас · {formatLongDate(new Date(now).toISOString())}
          </span>
        </span>
      </div>
      <span className="flex items-center pl-4 text-[11px] text-text-secondary">Пролёты S2</span>
      <p className="col-start-2 row-span-2 flex items-center font-serif text-[13px] text-text-tertiary italic">
        {message}
      </p>
    </div>
  );
}
