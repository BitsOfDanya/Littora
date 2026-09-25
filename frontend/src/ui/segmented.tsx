"use client";

import type { ReactNode } from "react";
import { cn } from "./cn";

export type SegmentOption<T extends string> = {
  value: T;
  label: ReactNode;
  title?: string;
  disabled?: boolean;
  disabledReason?: string;
};

type SegmentedProps<T extends string> = {
  label: string;
  value: T | null;
  options: readonly SegmentOption<T>[];
  onChange: (value: T) => void;
  size?: "sm" | "md";
  stretch?: boolean;
  className?: string;
};

export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
  size = "sm",
  stretch,
  className,
}: SegmentedProps<T>) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={cn(
        "inline-flex gap-px rounded-[var(--radius-ctl)] border border-line-control bg-surface-sunken p-px",
        stretch && "flex w-full",
        className,
      )}
    >
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-disabled={option.disabled || undefined}
            title={option.disabled ? option.disabledReason : option.title}
            onClick={() => {
              if (!option.disabled) onChange(option.value);
            }}
            className={cn(
              "inline-flex items-center justify-center gap-1.5 rounded-[1px] px-2.5 whitespace-nowrap text-text-secondary transition-colors duration-[var(--t-2)] hover:bg-surface-raised hover:text-text-primary",
              size === "sm" ? "h-6 text-[12px]" : "h-7 text-[13px]",
              stretch && "flex-1",
              selected &&
                "bg-surface-raised font-semibold text-text-primary shadow-[inset_0_0_0_1px_var(--text-primary)]",
              option.disabled &&
                "cursor-not-allowed text-text-disabled line-through decoration-dotted hover:bg-transparent hover:text-text-disabled",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
