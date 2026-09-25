"use client";

import type { KeyboardEvent } from "react";
import { FORECAST_HORIZONS_H, type ForecastHorizonH } from "@/domain/forecast";
import { cn } from "@/ui/cn";
import { reliabilityOf, RELIABILITY_WORD } from "./drift-math";

type HorizonSegProps = {
  value: ForecastHorizonH;
  onChange: (horizonH: ForecastHorizonH) => void;
  disabled?: boolean;
  size?: "sm" | "md";
  label?: string;
  className?: string;
};

export function HorizonSeg({
  value,
  onChange,
  disabled,
  size = "sm",
  label = "Горизонт прогноза",
  className,
}: HorizonSegProps) {
  const handleKey = (event: KeyboardEvent<HTMLButtonElement>) => {
    const delta = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!delta) return;
    event.preventDefault();
    const index = FORECAST_HORIZONS_H.indexOf(value) + delta;
    const next = FORECAST_HORIZONS_H[Math.min(Math.max(index, 0), FORECAST_HORIZONS_H.length - 1)];
    onChange(next);
    const group = event.currentTarget.parentElement;
    requestAnimationFrame(() =>
      group?.querySelector<HTMLButtonElement>(`[data-horizon="${next}"]`)?.focus(),
    );
  };

  return (
    <div className={cn("inline-flex items-center gap-1.5", className)}>
      <div
        role="radiogroup"
        aria-label={label}
        className={cn(
          "inline-flex gap-px rounded-[var(--radius-ctl)] border border-line-control bg-surface-sunken p-px",
          disabled && "border-dashed",
        )}
      >
        {FORECAST_HORIZONS_H.map((hour) => {
          const selected = hour === value;
          return (
            <button
              key={hour}
              type="button"
              role="radio"
              aria-checked={selected}
              data-horizon={hour}
              tabIndex={selected ? 0 : -1}
              disabled={disabled}
              title={`+${hour} ч · надёжность ${RELIABILITY_WORD[reliabilityOf(hour)]}`}
              onClick={() => onChange(hour)}
              onKeyDown={handleKey}
              className={cn(
                "inline-flex min-w-9 items-center justify-center rounded-[1px] px-1.5 font-mono whitespace-nowrap text-text-secondary transition-colors duration-[var(--t-2)] hover:bg-surface-raised hover:text-text-primary",
                size === "sm" ? "h-6 text-[12px]" : "h-7 text-[13px]",
                selected &&
                  "bg-accent-selection font-semibold text-text-inverse hover:bg-accent-selection hover:text-text-inverse",
                disabled &&
                  "cursor-not-allowed text-text-disabled hover:bg-transparent hover:text-text-disabled",
              )}
            >
              +{hour}
            </button>
          );
        })}
      </div>
      <span className="text-[12px] text-text-secondary">ч</span>
    </div>
  );
}
