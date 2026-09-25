"use client";

import { colorForValue } from "@/features/map/color";
import { rampFor } from "@/features/map/ramps";
import { usePreferencesStore } from "@/state/preferences-store";

const RANGE_PP = 10;

export function useUiChangeRamp() {
  const theme = usePreferencesStore((state) => state.theme);
  return rampFor("change", theme === "day" ? "light" : "dark");
}

export function DeltaBar({ deltaPp, width = 64 }: { deltaPp: number | null; width?: number }) {
  const ramp = useUiChangeRamp();
  const half = width / 2;
  const clamped = deltaPp === null ? 0 : Math.max(-RANGE_PP, Math.min(RANGE_PP, deltaPp));
  const length = (Math.abs(clamped) / RANGE_PP) * half;
  const color = deltaPp === null ? "transparent" : colorForValue(ramp, deltaPp);
  return (
    <svg width={width} height={8} aria-hidden className="block shrink-0 overflow-visible">
      <rect x={0} y={0} width={width} height={8} fill="var(--surface-sunken)" />
      {deltaPp !== null && length > 0 ? (
        <rect
          x={clamped < 0 ? half - length : half}
          y={0}
          width={length}
          height={8}
          fill={color}
          stroke="var(--line-control)"
          strokeWidth={0.5}
        />
      ) : null}
      <line x1={half} x2={half} y1={-2} y2={10} stroke="var(--text-secondary)" strokeWidth={1} />
    </svg>
  );
}

export function DeltaLegend({ width = 64 }: { width?: number }) {
  const ramp = useUiChangeRamp();
  const cell = width / ramp.colors.length;
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="font-mono text-[10.5px] text-text-tertiary">−10</span>
      <svg width={width} height={8} aria-hidden className="block">
        {ramp.colors.map((color, index) => (
          <rect key={color} x={index * cell} y={0} width={cell} height={8} fill={color} />
        ))}
        <rect
          x={0.5}
          y={0.5}
          width={width - 1}
          height={7}
          fill="none"
          stroke="var(--line-control)"
          strokeWidth={0.5}
        />
      </svg>
      <span className="font-mono text-[10.5px] text-text-tertiary">+10</span>
      <span className="text-[11px] text-text-tertiary">п.&nbsp;п.</span>
    </span>
  );
}
