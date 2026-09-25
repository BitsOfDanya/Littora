"use client";

import { motion } from "motion/react";
import { cn } from "@/ui/cn";
import type { LeafSide } from "./draw-engraving";
import { CHAMBER_DEPTH_M, isOpeningRun } from "./gate-choreography";
import { GATE_LIVERY } from "./gate-livery";
import { useGateStore } from "./gate-store";
import { useGateValue } from "./use-gate-value";

const RANGE_CM = 400;

type StaffScale = { width: number; pxPerCm: number; labelled: boolean };

const DESKTOP_STAFF: StaffScale = { width: 44, pxPerCm: 1.5, labelled: true };
const PHONE_STAFF: StaffScale = { width: 12, pxPerCm: 1.1, labelled: false };

function tickLength(cm: number, { width, labelled }: StaffScale): number | null {
  if (cm % 100 === 0) return labelled ? width * 0.5 : width;
  if (cm % 50 === 0) return labelled ? width * 0.38 : width * 0.6;
  if (cm % 10 === 0) return labelled ? width * 0.26 : width * 0.34;
  return labelled ? width * 0.12 : null;
}

function metreLabel(cm: number, side: LeafSide): string {
  if (cm === 0) return "0";
  return `${side === "upper" ? "+" : "−"}${cm / 100}`;
}

function Staff({
  side,
  scale,
  className,
}: {
  side: LeafSide;
  scale: StaffScale;
  className?: string;
}) {
  const height = RANGE_CM * scale.pxPerCm;
  const yOf = (cm: number) => (side === "upper" ? height - cm * scale.pxPerCm : cm * scale.pxPerCm);
  const step = scale.labelled ? 2 : 10;
  const ticks = Array.from({ length: RANGE_CM / step + 1 }, (_, index) => index * step);
  return (
    <svg
      aria-hidden
      width={scale.width}
      height={height}
      viewBox={`0 0 ${scale.width} ${height}`}
      className={cn("absolute", side === "upper" ? "bottom-0" : "top-0", className)}
    >
      <rect
        x={0.5}
        y={0.5}
        width={scale.width - 1}
        height={height - 1}
        fill={GATE_LIVERY.stamp}
        stroke={GATE_LIVERY.ink}
      />
      {side === "lower" ? (
        <rect
          x={1}
          y={1}
          width={scale.width - 2}
          height={height - 2}
          fill={GATE_LIVERY.staffWater}
        />
      ) : null}
      {ticks.map((cm) => {
        const length = tickLength(cm, scale);
        if (length === null) return null;
        const y = Math.round(yOf(cm)) + 0.5;
        return (
          <line
            key={cm}
            x1={1}
            x2={length}
            y1={y}
            y2={y}
            stroke={GATE_LIVERY.ink}
            strokeWidth={cm % 100 === 0 ? 1.6 : cm % 10 === 0 ? 1 : 0.6}
          />
        );
      })}
      {scale.labelled
        ? ticks
            .filter((cm) => cm % 100 === 0 && (cm > 0 || side === "upper"))
            .map((cm) => (
              <text
                key={`label-${cm}`}
                x={scale.width - 4}
                y={yOf(cm) + (cm === 0 ? -5 : 4.5)}
                textAnchor="end"
                className="font-mono"
                fontSize={12}
                fontWeight={600}
                fill={GATE_LIVERY.ink}
                stroke={GATE_LIVERY.stamp}
                strokeWidth={3}
                paintOrder="stroke"
              >
                {metreLabel(cm, side)}
              </text>
            ))
        : null}
    </svg>
  );
}

export function StaffHalf({ side }: { side: LeafSide }) {
  return (
    <>
      <Staff side={side} scale={DESKTOP_STAFF} className="right-[10px] hidden md:block" />
      <Staff side={side} scale={PHONE_STAFF} className="right-0 md:hidden" />
    </>
  );
}

export function LevelPointer() {
  const run = useGateStore((state) => state.run);
  const opening = isOpeningRun(run);
  const transform = useGateValue((frame) => {
    const depth = opening ? CHAMBER_DEPTH_M * (1 - frame.equalised) : CHAMBER_DEPTH_M;
    return `translateY(calc(var(--gauge-ppm) * ${depth.toFixed(4)}))`;
  });
  const opacity = useGateValue((frame) => frame.pointerOpacity);
  return (
    <motion.div
      aria-hidden
      className={cn(
        "pointer-events-none absolute inset-x-0 top-(--seam) z-10 h-0",
        run === null && "transition-transform duration-(--t-5) ease-(--e-std)",
      )}
      style={{ transform, opacity }}
    >
      <span className="absolute right-0 h-0.5 w-3 -translate-y-1/2 bg-(--gate-ink) md:right-[10px] md:w-11" />
      <span className="absolute right-3 size-0 -translate-y-1/2 border-y-4 border-l-[5px] border-y-transparent border-l-(--gate-ink) md:right-[54px] md:border-y-[6px] md:border-l-[7px]" />
    </motion.div>
  );
}
