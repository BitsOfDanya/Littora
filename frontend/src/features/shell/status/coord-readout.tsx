"use client";

import { useMapViewStore } from "@/features/map/state/map-view-store";
import { type CoordinateFormat, formatLngLat } from "@/lib/format/coordinates";
import { formatNumber } from "@/lib/format/numbers";
import { usePreferencesStore } from "@/state/preferences-store";
import { cn } from "@/ui/cn";
import { useHydrated } from "../layout/use-environment";

type FormatOption = { value: CoordinateFormat | "mgrs"; label: string; disabledReason?: string };

const FORMAT_OPTIONS: readonly FormatOption[] = [
  { value: "dd", label: "DD" },
  { value: "dm", label: "DM" },
  { value: "mgrs", label: "MGRS", disabledReason: "MGRS появится в следующей версии" },
];

export function useCoordinateFormat(): CoordinateFormat {
  const stored = usePreferencesStore((state) => state.coordinateFormat);
  return useHydrated() ? stored : "dm";
}

export function CoordinateText({
  prefix = true,
  className,
}: {
  prefix?: boolean;
  className?: string;
}) {
  const cursor = useMapViewStore((state) => state.cursor);
  const center = useMapViewStore((state) => state.center);
  const isReady = useMapViewStore((state) => state.isReady);
  const format = useCoordinateFormat();
  const point = cursor ?? center;
  const label = cursor ? "Курсор" : "Центр";
  return (
    <span
      className={cn("inline-flex items-baseline gap-1.5 whitespace-nowrap", className)}
      aria-live="off"
    >
      {prefix ? <span className="text-text-tertiary">{label}</span> : null}
      <span className="font-mono text-text-primary">
        {isReady ? formatLngLat(point, format).replace("  ", " ") : "—"}
      </span>
    </span>
  );
}

export function CoordinateFormatSeg() {
  const format = useCoordinateFormat();
  const setFormat = usePreferencesStore((state) => state.setCoordinateFormat);
  return (
    <span
      role="radiogroup"
      aria-label="Формат координат"
      className="inline-flex h-[18px] rounded-[var(--radius-ctl)] border border-line-control"
    >
      {FORMAT_OPTIONS.map((option) => {
        const selected = option.value === format;
        const disabled = option.disabledReason !== undefined;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-disabled={disabled || undefined}
            title={option.disabledReason ?? `Координаты: ${option.label}`}
            onClick={() => {
              if (option.value !== "mgrs") setFormat(option.value);
            }}
            className={cn(
              "px-1.5 font-mono text-[11px] leading-4 text-text-secondary hover:text-text-primary",
              selected && "bg-primary-fill text-primary-text hover:text-primary-text",
              disabled &&
                "cursor-not-allowed text-text-disabled line-through decoration-dotted hover:text-text-disabled",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </span>
  );
}

export function formatScale(denominator: number): string {
  if (!Number.isFinite(denominator) || denominator <= 0) return "—";
  const magnitude = 10 ** Math.max(0, Math.floor(Math.log10(denominator)) - 2);
  return `1:${formatNumber(Math.round(denominator / magnitude) * magnitude)}`;
}

export function ScaleText() {
  const denominator = useMapViewStore((state) => state.scaleDenominator);
  return <span className="font-mono text-text-primary">{formatScale(denominator)}</span>;
}

export function ZoomText() {
  const zoom = useMapViewStore((state) => state.zoom);
  return <span className="font-mono text-text-primary">z {formatNumber(zoom, 1)}</span>;
}
