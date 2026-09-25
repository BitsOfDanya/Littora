"use client";

import {
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
  type RefObject,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import type { SceneSummary } from "@/domain/scene";
import { GROUND_INK } from "@/features/map/palette";
import { NO_DATA } from "@/features/map/ramps";
import { useFrameWidth, useIsPhoneWidth } from "@/features/map/furniture/use-frame-width";
import { useMainMap } from "@/features/map/use-main-map";
import { useGround } from "@/features/map/use-map-palette";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { formatPercent } from "@/lib/format/numbers";
import { formatUtcDateTime } from "@/lib/format/time";
import { useWorkspaceStore } from "@/state/workspace-store";
import { cn } from "@/ui/cn";
import { SeverityGlyph } from "@/ui/indicators";
import {
  type CompareSide,
  type DividerAction,
  isUsable,
  MOSAIC_YEARS,
  nextDividerPosition,
} from "./compare-model";
import { useCompareViewStore } from "./compare-view-store";
import { useCompareData } from "./use-compare";

const CHIP_GAP_PX = 10;
const CHIP_TOP_PX = 48;
const CHIP_STACK_PX = 34;
const CHIP_ROOM_PX = 280;
const KNOB = { desktop: { width: 32, height: 44 }, phone: { width: 40, height: 48 } } as const;
const HIT_STRIP_PX = 12;
const DIVIDER_HINT = "Шторка: перетащите или , . — шаг 5 %, с Shift — 20 %";

const KEY_ACTIONS: Readonly<Record<string, DividerAction>> = {
  ArrowLeft: "decrease",
  ArrowDown: "decrease",
  ArrowRight: "increase",
  ArrowUp: "increase",
  PageDown: "decrease",
  PageUp: "increase",
  Home: "start",
  End: "end",
};

function useDividerView(
  elementRef: RefObject<HTMLDivElement | null>,
  position: number,
  frame: number,
): void {
  const map = useMainMap();
  const setView = useCompareViewStore((state) => state.setView);

  useEffect(() => {
    const element = elementRef.current;
    if (!map || !element) return;
    const update = () => {
      const rect = element.getBoundingClientRect();
      const canvasRect = map.getCanvas().getBoundingClientRect();
      if (!rect.width || !canvasRect.width) return;
      const x = rect.left - canvasRect.left + frame + position * (rect.width - 2 * frame);
      const y = rect.top - canvasRect.top + rect.height / 2;
      setView(map.unproject([x, y]).lng, map.getZoom());
    };
    update();
    map.on("move", update);
    map.on("resize", update);
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => {
      map.off("move", update);
      map.off("resize", update);
      observer.disconnect();
    };
  }, [map, elementRef, position, frame, setView]);
}

function hatchStyle(ground: "dark" | "light"): CSSProperties {
  const ink = NO_DATA.ink[ground];
  const line = GROUND_INK[ground].nodata;
  const spacing = NO_DATA.spacingPx;
  const stroke = `color-mix(in srgb, ${line} ${NO_DATA.lineAlpha * 100}%, transparent)`;
  return {
    backgroundColor: ink.underlay,
    backgroundImage: [45, -45]
      .map(
        (angle) =>
          `repeating-linear-gradient(${angle}deg, ${stroke} 0 1px, transparent 1px ${spacing}px)`,
      )
      .join(", "),
  };
}

function sceneLabel(scene: SceneSummary): string {
  return formatUtcDateTime(scene.acquiredAt);
}

function chipPlacement(
  x: number,
  width: number,
  frame: number,
): Record<CompareSide, CSSProperties> {
  const leftRoom = x - frame;
  const rightRoom = width - frame - x;
  const top = CHIP_TOP_PX;
  const stacked = top + CHIP_STACK_PX;
  if (leftRoom < CHIP_ROOM_PX)
    return { a: { left: CHIP_GAP_PX, top: stacked }, b: { left: CHIP_GAP_PX, top } };
  if (rightRoom < CHIP_ROOM_PX)
    return { a: { right: CHIP_GAP_PX, top }, b: { right: CHIP_GAP_PX, top: stacked } };
  return { a: { right: CHIP_GAP_PX, top }, b: { left: CHIP_GAP_PX, top } };
}

function DateChip({
  side,
  scene,
  style,
}: {
  side: CompareSide;
  scene: SceneSummary | null;
  style: CSSProperties;
}) {
  const letter = side === "a" ? "A" : "B";
  const cloudy = scene !== null && !isUsable(scene);
  return (
    <div
      className="absolute flex h-7 items-center gap-1.5 border border-line-control bg-surface-panel pr-2 pl-[3px] font-mono text-[12px] leading-none whitespace-nowrap text-text-primary"
      style={style}
    >
      <span
        aria-hidden
        className="grid size-5 place-items-center bg-primary-fill font-sans text-[11px] font-bold text-primary-text"
      >
        {letter}
      </span>
      <span className="sr-only">{side === "a" ? "Дата A" : "Дата B"}</span>
      <span>{scene ? sceneLabel(scene) : `мозаика ${MOSAIC_YEARS[side]}`}</span>
      {cloudy ? (
        <span className="inline-flex items-center gap-1 font-sans text-state-caution">
          <SeverityGlyph severity="caution" size={12} />
          облачно {formatPercent(scene.cloudCover)}
        </span>
      ) : null}
    </div>
  );
}

function GripDots() {
  return (
    <span aria-hidden className="grid grid-cols-2 gap-x-[5px] gap-y-[5px]">
      {Array.from({ length: 6 }, (_, index) => (
        <span key={index} className="block size-[3px] rounded-full bg-text-secondary" />
      ))}
    </span>
  );
}

type KnobProps = {
  position: number;
  disabled: boolean;
  phone: boolean;
  valueText: string;
  dragging: boolean;
  onAction: (action: DividerAction, large: boolean) => void;
  dragHandlers: DragHandlers;
};

function Knob({
  position,
  disabled,
  phone,
  valueText,
  dragging,
  onAction,
  dragHandlers,
}: KnobProps) {
  const setHint = useStatusHintStore((state) => state.setHint);
  const size = phone ? KNOB.phone : KNOB.desktop;
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const action = KEY_ACTIONS[event.key];
    if (!action || disabled) return;
    event.preventDefault();
    event.stopPropagation();
    onAction(action, event.shiftKey || event.key.startsWith("Page"));
  };
  return (
    <div
      role="slider"
      tabIndex={0}
      aria-label="Шторка сравнения A/B"
      aria-orientation="horizontal"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(position * 100)}
      aria-valuetext={valueText}
      aria-disabled={disabled || undefined}
      title={disabled ? undefined : `${DIVIDER_HINT} · Home/End — к краю`}
      onKeyDown={handleKeyDown}
      onMouseEnter={() => setHint(disabled ? null : DIVIDER_HINT)}
      onMouseLeave={() => setHint(null)}
      {...(disabled ? {} : dragHandlers)}
      className={cn(
        "pointer-events-auto absolute top-1/2 grid -translate-x-1/2 -translate-y-1/2 touch-none place-items-center rounded-[var(--radius-ctl)] border bg-surface-panel select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus-ring",
        disabled
          ? "cursor-not-allowed border-dashed border-line-control"
          : "cursor-ew-resize border-text-primary hover:bg-surface-raised",
        dragging && "border-2 bg-surface-raised",
      )}
      style={{ left: 0, width: size.width, height: size.height }}
    >
      {disabled ? null : <GripDots />}
    </div>
  );
}

type DragHandlers = {
  onPointerDown: (event: PointerEvent<HTMLElement>) => void;
  onPointerMove: (event: PointerEvent<HTMLElement>) => void;
  onPointerUp: (event: PointerEvent<HTMLElement>) => void;
  onPointerCancel: (event: PointerEvent<HTMLElement>) => void;
};

function useDividerDrag(
  elementRef: RefObject<HTMLDivElement | null>,
  frame: number,
  onPosition: (position: number) => void,
): { dragging: boolean; handlers: DragHandlers } {
  const [dragging, setDragging] = useState(false);
  const positionFor = useCallback(
    (clientX: number) => {
      const rect = elementRef.current?.getBoundingClientRect();
      if (!rect) return null;
      const span = rect.width - 2 * frame;
      if (span <= 0) return null;
      return Math.min(1, Math.max(0, (clientX - rect.left - frame) / span));
    },
    [elementRef, frame],
  );
  const move = (event: PointerEvent<HTMLElement>) => {
    const next = positionFor(event.clientX);
    if (next !== null) onPosition(Math.round(next * 1000) / 1000);
  };
  const end = (event: PointerEvent<HTMLElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId))
      event.currentTarget.releasePointerCapture(event.pointerId);
    setDragging(false);
  };
  return {
    dragging,
    handlers: {
      onPointerDown: (event) => {
        if (event.button !== 0) return;
        event.preventDefault();
        event.currentTarget.setPointerCapture(event.pointerId);
        setDragging(true);
        move(event);
      },
      onPointerMove: (event) => {
        if (event.currentTarget.hasPointerCapture(event.pointerId)) move(event);
      },
      onPointerUp: end,
      onPointerCancel: end,
    },
  };
}

function valueTextOf(position: number, a: SceneSummary | null, b: SceneSummary | null): string {
  const left = a ? `A ${sceneLabel(a)}` : `A мозаика ${MOSAIC_YEARS.a}`;
  const right = b ? `B ${sceneLabel(b)}` : `B мозаика ${MOSAIC_YEARS.b}`;
  return `${Math.round(position * 100)} % · слева ${left}, справа ${right}`;
}

function DisabledNote({ usable }: { usable: number }) {
  return (
    <p className="pointer-events-auto absolute top-1/2 left-[28px] w-64 -translate-y-1/2 border border-dashed border-line-control bg-surface-panel px-2.5 py-2 text-[12px] leading-4 text-text-secondary">
      Для сравнения нужны два пригодных снимка. Пригодных в окне: {usable}.
    </p>
  );
}

function SideHatch({ from, to, ground }: { from: number; to: number; ground: "dark" | "light" }) {
  if (to <= from) return null;
  return (
    <div
      aria-hidden
      className="absolute inset-y-0"
      style={{ left: from, width: to - from, ...hatchStyle(ground) }}
    />
  );
}

export function CompareDivider(): ReactNode {
  const elementRef = useRef<HTMLDivElement>(null);
  const frame = useFrameWidth();
  const phone = useIsPhoneWidth();
  const ground = useGround();
  const position = useWorkspaceStore((state) => state.compare.position);
  const updateCompare = useWorkspaceStore((state) => state.updateCompare);
  const { pair, hasCatalog, enoughUsable, usable } = useCompareData();
  const [width, setWidth] = useState(0);
  const setPosition = useCallback(
    (next: number) => updateCompare({ position: next }),
    [updateCompare],
  );
  const { dragging, handlers } = useDividerDrag(elementRef, frame, setPosition);
  const disabled = hasCatalog && !enoughUsable;

  useDividerView(elementRef, position, frame);

  useEffect(() => {
    const element = elementRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const a = pair?.a ?? null;
  const b = pair?.b ?? null;
  const x = frame + position * Math.max(0, width - 2 * frame);
  const ink = GROUND_INK[ground];

  const chips = chipPlacement(x, width, frame);
  const column = { left: x, top: frame, bottom: frame, width: 0 };

  return (
    <>
      <div
        ref={elementRef}
        className="pointer-events-none absolute inset-0 -z-10 overflow-hidden"
        data-dragging={dragging || undefined}
      >
        {width > 0 && !disabled ? (
          <>
            {a && !isUsable(a) ? <SideHatch from={frame} to={x} ground={ground} /> : null}
            {b && !isUsable(b) ? <SideHatch from={x} to={width - frame} ground={ground} /> : null}
          </>
        ) : null}
        {width > 0 ? (
          <div
            aria-hidden
            className={cn("absolute", disabled && "opacity-40")}
            style={{
              ...column,
              marginLeft: -1,
              width: 2,
              background: ink.label,
              boxShadow: `0 0 0 1px ${ink.halo}`,
            }}
          />
        ) : null}
      </div>
      {width > 0 ? (
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute" style={column}>
            {disabled ? null : (
              <div
                aria-hidden
                className="pointer-events-auto absolute inset-y-0 cursor-ew-resize touch-none"
                style={{ left: -HIT_STRIP_PX / 2, width: HIT_STRIP_PX }}
                {...handlers}
              />
            )}
            <Knob
              position={position}
              disabled={disabled}
              phone={phone}
              dragging={dragging}
              valueText={valueTextOf(position, a, b)}
              onAction={(action, large) =>
                setPosition(nextDividerPosition(position, action, large))
              }
              dragHandlers={handlers}
            />
            {disabled ? <DisabledNote usable={usable} /> : null}
            {disabled ? null : (
              <>
                <DateChip side="a" scene={a} style={chips.a} />
                <DateChip side="b" scene={b} style={chips.b} />
              </>
            )}
          </div>
        </div>
      ) : null}
    </>
  );
}
