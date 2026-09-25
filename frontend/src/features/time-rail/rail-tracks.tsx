"use client";

import {
  type KeyboardEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { SceneSummary } from "@/domain/scene";
import { formatNumber, formatPercent } from "@/lib/format/numbers";
import { monthShortName } from "@/lib/format/time";
import { cn } from "@/ui/cn";
import { DemoTag } from "@/ui/demo-mark";
import { type Severity, SeverityGlyph } from "@/ui/indicators";
import { IconDiamond } from "@/ui/icons";
import { spreadMarks } from "./rail-model";
import {
  clampWindow,
  DAY,
  fromRatio,
  isSameWindow,
  panWindow,
  type TimeWindow,
  toRatio,
  zoomWindow,
} from "./time-scale";

export const LANES = { axis: 14, passes: 22, signal: 30, events: 18 } as const;
const LANE_TOP = {
  axis: 0,
  passes: LANES.axis,
  signal: LANES.axis + LANES.passes,
  events: LANES.axis + LANES.passes + LANES.signal,
} as const;
const LANES_HEIGHT = LANE_TOP.events + LANES.events;
const LABEL_COLUMN = "grid-cols-[120px_minmax(0,1fr)]";
const TICK_STEPS_DAYS = [1, 2, 5, 10, 15] as const;
const MIN_TICK_GAP_PX = 26;
const PERCENT_LABEL_GAP_PX = 30;
const EVENT_STEP_PX = 13;
const MAX_BAR_PX = LANES.signal - 6;

export const USABILITY_WORD: Record<SceneSummary["usability"], string> = {
  usable: "пригоден",
  partial: "частично облачно",
  unusable: "непригоден",
};

const pad = (value: number) => String(value).padStart(2, "0");

export function passStamp(iso: string): string {
  const date = new Date(iso);
  return `${pad(date.getUTCDate())}.${pad(date.getUTCMonth() + 1)}.${date.getUTCFullYear()} ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}Z`;
}

export function shortDay(iso: string | number): string {
  const date = new Date(iso);
  return `${pad(date.getUTCDate())}.${pad(date.getUTCMonth() + 1)}`;
}

export function passTooltip(scene: SceneSummary): string {
  return `${passStamp(scene.acquiredAt)} · ${scene.platform} · облачность ${formatPercent(scene.cloudCover)} · ${USABILITY_WORD[scene.usability]}`;
}

export type PassSignal = { areaM2: number | null; partial: boolean; found: number };

export type EventMark = {
  id: string;
  at: string;
  severity: Severity;
  acknowledged: boolean;
  operator: boolean;
  tooltip: string;
};

export type PlannedMark = { at: string; label: string };

type Tip = { x: number; text: string } | null;

export function useLaneWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return { ref, width };
}

export function useZoomableWindow(bounds: TimeWindow, element: HTMLElement | null) {
  const [view, setView] = useState<TimeWindow | null>(null);
  const boundsRef = useRef(bounds);
  useEffect(() => {
    boundsRef.current = bounds;
  });

  useEffect(() => {
    if (!element) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = element.getBoundingClientRect();
      setView((current) => {
        const base = current ?? boundsRef.current;
        const horizontal = event.shiftKey || Math.abs(event.deltaX) > Math.abs(event.deltaY);
        const delta = horizontal ? event.deltaX || event.deltaY : event.deltaY;
        const next = horizontal
          ? panWindow(base, delta / Math.max(rect.width, 1))
          : zoomWindow(
              base,
              fromRatio(base, (event.clientX - rect.left) / Math.max(rect.width, 1)),
              Math.exp(delta * 0.0015),
            );
        const clamped = clampWindow(next, boundsRef.current);
        return isSameWindow(clamped, boundsRef.current) ? null : clamped;
      });
    };
    element.addEventListener("wheel", onWheel, { passive: false });
    return () => element.removeEventListener("wheel", onWheel);
  }, [element]);

  return { window: view ?? bounds, zoomed: view !== null, reset: () => setView(null) };
}

function tickStep(window: TimeWindow, width: number): number {
  const pxPerDay = width / Math.max((window.end - window.start) / DAY, 1);
  return TICK_STEPS_DAYS.find((step) => step * pxPerDay >= MIN_TICK_GAP_PX) ?? 30;
}

const MONTH_LABEL_PX = 58;
const DAY_LABEL_PX = 18;

function axisTicks(window: TimeWindow, width: number, avoid: readonly number[]) {
  const step = tickStep(window, width);
  const px = (at: number) => toRatio(window, at) * width;
  const months: { at: number; label: string; month: boolean }[] = [];
  const days: { at: number; label: string; month: boolean }[] = [];
  const cursor = new Date(window.start);
  cursor.setUTCHours(0, 0, 0, 0);
  cursor.setUTCDate(cursor.getUTCDate() + 1);
  while (cursor.getTime() <= window.end) {
    const day = cursor.getUTCDate();
    if (day === 1)
      months.push({
        at: cursor.getTime(),
        label: `${monthShortName(cursor.getUTCMonth())} ${cursor.getUTCFullYear()}`,
        month: true,
      });
    else if (day % step === 0)
      days.push({ at: cursor.getTime(), label: String(day), month: false });
    cursor.setUTCDate(day + 1);
  }
  const blocked = [
    ...months.map((tick) => [px(tick.at) - DAY_LABEL_PX, px(tick.at) + MONTH_LABEL_PX]),
    ...avoid.map((at) => [px(at) - 46, px(at) + 30]),
  ];
  const freeDays = days.filter((tick) => {
    const x = px(tick.at);
    return x + DAY_LABEL_PX <= width && blocked.every(([from, to]) => x < from || x > to);
  });
  return [...months.filter((tick) => px(tick.at) + MONTH_LABEL_PX <= width + 20), ...freeDays];
}

export function TrackLabel({
  children,
  demo,
  className,
}: {
  children: ReactNode;
  demo?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "flex min-w-0 items-center gap-1.5 pr-2 text-[11px] leading-[13px] text-text-secondary",
        className,
      )}
    >
      <span className="whitespace-nowrap">{children}</span>
      {demo ? <DemoTag /> : null}
    </span>
  );
}

export function TrackFrame({ labels, lanes }: { labels: ReactNode; lanes: ReactNode }) {
  return (
    <div
      className={cn("grid h-full min-w-0 content-center gap-y-0 pr-4 pl-3", LABEL_COLUMN)}
      style={{
        gridTemplateRows: `${LANES.axis}px ${LANES.passes}px ${LANES.signal}px ${LANES.events}px`,
      }}
    >
      {labels}
      <div className="relative col-start-2 row-span-4 row-start-1 min-w-0">{lanes}</div>
    </div>
  );
}

function Ticks({
  window,
  width,
  avoid,
}: {
  window: TimeWindow;
  width: number;
  avoid: readonly number[];
}) {
  const ticks = useMemo(() => axisTicks(window, width, avoid), [window, width, avoid]);
  return (
    <>
      {ticks.map((tick) => (
        <span
          key={tick.at}
          aria-hidden
          style={{ left: `${toRatio(window, tick.at) * 100}%`, height: LANES_HEIGHT }}
          className={cn(
            "pointer-events-none absolute top-0 border-l pl-1 font-mono text-[10.5px] leading-3 whitespace-nowrap",
            tick.month
              ? "border-line-control text-text-secondary"
              : "border-line-hairline/70 text-text-tertiary",
          )}
        >
          {tick.label}
        </span>
      ))}
    </>
  );
}

export function NowMarker({
  window,
  now,
  label,
  futureLabel,
}: {
  window: TimeWindow;
  now: number;
  label: string;
  futureLabel: string | null;
}) {
  const ratio = toRatio(window, now);
  if (ratio > 1) return null;
  const left = `${Math.max(ratio, 0) * 100}%`;
  return (
    <>
      <span
        aria-hidden
        className="future-hatch pointer-events-none absolute right-0 border-l border-line-hairline"
        style={{ left, top: LANE_TOP.passes, height: LANES_HEIGHT - LANE_TOP.passes }}
      />
      {futureLabel ? (
        <span
          aria-hidden
          className="pointer-events-none absolute pl-1.5 font-mono text-[10.5px] leading-3 whitespace-nowrap text-text-tertiary"
          style={{ left, top: LANE_TOP.signal + 17 }}
        >
          {futureLabel}
        </span>
      ) : null}
      {ratio >= 0 ? (
        <>
          <span
            aria-hidden
            className="pointer-events-none absolute w-px bg-text-primary"
            style={{ left, top: LANE_TOP.passes - 2, height: LANES_HEIGHT - LANE_TOP.passes + 2 }}
          />
          <span
            className="pointer-events-none absolute top-0 -translate-x-1/2 bg-surface-panel px-1 font-mono text-[10.5px] leading-3 font-medium whitespace-nowrap text-text-primary"
            style={{ left }}
          >
            {label}
          </span>
        </>
      ) : null}
    </>
  );
}

export function Cursor({ window, at }: { window: TimeWindow; at: number }) {
  const ratio = toRatio(window, at);
  if (ratio < 0 || ratio > 1) return null;
  const left = `${ratio * 100}%`;
  return (
    <>
      <span
        aria-hidden
        className="pointer-events-none absolute w-0.5 -translate-x-1/2 bg-accent-selection"
        style={{ left, top: LANE_TOP.axis + 6, height: LANES_HEIGHT - 6 }}
      />
      <span
        aria-hidden
        className="pointer-events-none absolute -translate-x-1/2 border-x-[5px] border-t-[6px] border-x-transparent border-t-accent-selection"
        style={{ left, top: LANE_TOP.axis + 2 }}
      />
    </>
  );
}

function PassSquare({
  scene,
  selected,
  planned,
}: {
  scene?: SceneSummary;
  selected?: boolean;
  planned?: boolean;
}) {
  const usability = scene?.usability;
  return (
    <span
      aria-hidden
      className={cn(
        "block size-2.5 border",
        planned && "border-dashed border-text-tertiary bg-surface-panel",
        usability === "usable" && "border-text-primary bg-text-primary",
        usability === "partial" && "border-text-primary bg-surface-panel",
        usability === "unusable" &&
          "border-text-tertiary bg-surface-panel bg-[repeating-linear-gradient(45deg,var(--text-tertiary)_0_1px,transparent_1px_3px)]",
        selected && "outline-2 outline-offset-1 outline-accent-selection",
      )}
    />
  );
}

export function PassLane({
  scenes,
  planned,
  selectedId,
  window,
  width,
  onSelect,
  onTip,
}: {
  scenes: readonly SceneSummary[];
  planned: readonly PlannedMark[];
  selectedId: string | null;
  window: TimeWindow;
  width: number;
  onSelect: (id: string) => void;
  onTip: (tip: Tip) => void;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const [focusIndex, setFocusIndex] = useState<number | null>(null);
  const selectedIndex = scenes.findIndex((scene) => scene.id === selectedId);
  const rovingIndex = focusIndex ?? (selectedIndex === -1 ? scenes.length - 1 : selectedIndex);
  const gapPx =
    scenes.length > 1
      ? (width * (Date.parse(scenes[1].acquiredAt) - Date.parse(scenes[0].acquiredAt))) /
        (window.end - window.start)
      : width;
  const showPercent = gapPx >= PERCENT_LABEL_GAP_PX;

  const focusPass = (index: number) => {
    const clamped = Math.min(Math.max(index, 0), scenes.length - 1);
    setFocusIndex(clamped);
    refs.current[clamped]?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const moves: Record<string, number> = {
      ArrowLeft: index - 1,
      ArrowRight: index + 1,
      Home: 0,
      End: scenes.length - 1,
    };
    if (!(event.key in moves)) return;
    event.preventDefault();
    focusPass(moves[event.key]);
  };

  const tipFor = (at: string, text: string) =>
    onTip({ x: toRatio(window, Date.parse(at)) * width, text });

  return (
    <div
      role="group"
      aria-label="Пролёты Sentinel-2: стрелки — между пролётами, Enter — выбрать"
      className="absolute inset-x-0"
      style={{ top: LANE_TOP.passes, height: LANES.passes }}
    >
      {scenes.map((scene, index) => {
        const ratio = toRatio(window, Date.parse(scene.acquiredAt));
        if (ratio < -0.02 || ratio > 1.02) return null;
        const selected = scene.id === selectedId;
        const text = passTooltip(scene);
        return (
          <button
            key={scene.id}
            ref={(element) => {
              refs.current[index] = element;
            }}
            type="button"
            tabIndex={index === rovingIndex ? 0 : -1}
            aria-label={text}
            aria-pressed={selected}
            onClick={() => onSelect(scene.id)}
            onKeyDown={(event) => onKeyDown(event, index)}
            onFocus={() => {
              setFocusIndex(index);
              tipFor(scene.acquiredAt, text);
            }}
            onBlur={() => {
              setFocusIndex(null);
              onTip(null);
            }}
            onMouseEnter={() => tipFor(scene.acquiredAt, text)}
            onMouseLeave={() => onTip(null)}
            style={{ left: `${ratio * 100}%` }}
            className="absolute top-1/2 grid h-[22px] w-3.5 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-[1px] focus-visible:outline-offset-0"
          >
            <PassSquare scene={scene} selected={selected} />
            {showPercent && scene.usability === "partial" ? (
              <span
                aria-hidden
                className="pointer-events-none absolute top-1/2 left-full -translate-y-1/2 pl-px font-mono text-[10.5px] leading-3 text-text-tertiary"
              >
                {Math.round(scene.cloudCover * 100)}%
              </span>
            ) : null}
          </button>
        );
      })}
      {planned.map((pass) => {
        const ratio = toRatio(window, Date.parse(pass.at));
        if (ratio < 0 || ratio > 1) return null;
        return (
          <span
            key={pass.at}
            role="img"
            aria-label={pass.label}
            onMouseEnter={() => tipFor(pass.at, pass.label)}
            onMouseLeave={() => onTip(null)}
            style={{ left: `${ratio * 100}%` }}
            className="absolute top-1/2 grid h-[22px] w-3.5 -translate-x-1/2 -translate-y-1/2 place-items-center"
          >
            <PassSquare planned />
          </span>
        );
      })}
    </div>
  );
}

export function SignalLane({
  scenes,
  signals,
  selectedId,
  window,
  width,
  onTip,
}: {
  scenes: readonly SceneSummary[];
  signals: Readonly<Record<string, PassSignal>>;
  selectedId: string | null;
  window: TimeWindow;
  width: number;
  onTip: (tip: Tip) => void;
}) {
  const max = Math.max(1, ...Object.values(signals).map((signal) => signal.areaM2 ?? 0));
  return (
    <div
      className="absolute inset-x-0 border-b border-line-hairline"
      style={{ top: LANE_TOP.signal, height: LANES.signal }}
    >
      {scenes.map((scene) => {
        const ratio = toRatio(window, Date.parse(scene.acquiredAt));
        if (ratio < -0.02 || ratio > 1.02) return null;
        const signal = signals[scene.id];
        const selected = scene.id === selectedId;
        const x = ratio * width;
        const day = shortDay(scene.acquiredAt);
        if (!signal || signal.areaM2 === null) {
          const text = `${day} · облачность ${formatPercent(scene.cloudCover)} — нет данных`;
          return (
            <span
              key={scene.id}
              onMouseEnter={() => onTip({ x, text })}
              onMouseLeave={() => onTip(null)}
              style={{ left: `${ratio * 100}%` }}
              className={cn(
                "absolute bottom-0.5 -translate-x-1/2 font-mono text-[11px] leading-3",
                selected ? "text-accent-selection" : "text-text-tertiary",
              )}
            >
              –
            </span>
          );
        }
        const areaKm2 = signal.areaM2 / 1_000_000;
        const text = `${day} · площадь ${formatNumber(areaKm2, 2)} км² · найдено ${signal.found}${signal.partial ? ` — неполно, облачность ${formatPercent(scene.cloudCover)}` : ""}`;
        const height = Math.max(1, Math.round((signal.areaM2 / max) * MAX_BAR_PX));
        return (
          <span
            key={scene.id}
            onMouseEnter={() => onTip({ x, text })}
            onMouseLeave={() => onTip(null)}
            style={{ left: `${ratio * 100}%`, height }}
            className={cn(
              "absolute bottom-0 w-1.5 -translate-x-1/2 border",
              signal.partial
                ? "border-text-secondary bg-surface-panel"
                : "border-text-secondary bg-text-secondary",
              selected && "border-accent-selection",
              selected && !signal.partial && "bg-accent-selection",
            )}
          />
        );
      })}
    </div>
  );
}

export function EventsLane({
  events,
  window,
  width,
  onTip,
}: {
  events: readonly EventMark[];
  window: TimeWindow;
  width: number;
  onTip: (tip: Tip) => void;
}) {
  const placed = useMemo(
    () =>
      spreadMarks(
        events.filter((event) => {
          const ratio = toRatio(window, Date.parse(event.at));
          return ratio >= 0 && ratio <= 1;
        }),
        (event) => toRatio(window, Date.parse(event.at)),
        width,
        EVENT_STEP_PX,
      ),
    [events, window, width],
  );
  return (
    <div className="absolute inset-x-0" style={{ top: LANE_TOP.events, height: LANES.events }}>
      {placed.map(({ item, ratio, offsetPx }) => {
        const x = ratio * width + offsetPx;
        return (
          <span
            key={item.id}
            role="img"
            aria-label={item.tooltip}
            onMouseEnter={() => onTip({ x, text: item.tooltip })}
            onMouseLeave={() => onTip(null)}
            style={{ left: x }}
            className="absolute top-1/2 grid size-3.5 -translate-x-1/2 -translate-y-1/2 place-items-center"
          >
            {item.operator ? (
              <IconDiamond size={10} className="text-text-secondary" />
            ) : (
              <SeverityGlyph severity={item.severity} acknowledged={item.acknowledged} size={12} />
            )}
          </span>
        );
      })}
    </div>
  );
}

export function TrackTooltip({ tip, width }: { tip: Tip; width: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [left, setLeft] = useState(0);
  const measure = useCallback(() => {
    const element = ref.current;
    if (!element || !tip) return;
    const half = element.offsetWidth / 2;
    setLeft(Math.min(Math.max(tip.x, half), Math.max(width - half, half)));
  }, [tip, width]);
  useEffect(measure, [measure]);
  if (!tip) return null;
  return (
    <span
      ref={ref}
      role="tooltip"
      className="pointer-events-none absolute z-20 -translate-x-1/2 rounded-[var(--radius-ctl)] bg-primary-fill px-2 py-0.5 text-[12px] leading-4 whitespace-nowrap text-primary-text"
      style={{ left, top: LANE_TOP.signal + 3 }}
    >
      {tip.text}
    </span>
  );
}

const NO_AVOID: readonly number[] = [];

export function AxisLane({
  window,
  width,
  avoid = NO_AVOID,
}: {
  window: TimeWindow;
  width: number;
  avoid?: readonly number[];
}) {
  return <Ticks window={window} width={width} avoid={avoid} />;
}

export { LANE_TOP, LANES_HEIGHT };
export type { Tip };
