"use client";

import type { ReactNode } from "react";
import { cn } from "./cn";

type CheckboxProps = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  disabledReason?: string;
  children: ReactNode;
  description?: ReactNode;
  trailing?: ReactNode;
  className?: string;
};

export function CheckboxBox({ checked, disabled }: { checked: boolean; disabled?: boolean }) {
  return (
    <span
      aria-hidden
      className={cn(
        "grid size-4 shrink-0 place-items-center rounded-[var(--radius-ctl)] border border-line-control bg-surface-raised text-primary-text",
        checked && "border-primary-fill bg-primary-fill",
        disabled && "border-dashed bg-transparent",
      )}
    >
      {checked ? (
        <svg
          viewBox="0 0 12 12"
          className="size-3"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.8}
          strokeLinecap="square"
        >
          <path d="M2.5 6.2l2.3 2.3 4.7-5" />
        </svg>
      ) : null}
    </span>
  );
}

export function Checkbox({
  checked,
  onChange,
  disabled,
  disabledReason,
  children,
  description,
  trailing,
  className,
}: CheckboxProps) {
  return (
    <label
      title={disabled ? disabledReason : undefined}
      className={cn(
        "group flex min-h-7 cursor-pointer items-start gap-2.5 py-1",
        disabled && "cursor-not-allowed",
        className,
      )}
    >
      <input
        type="checkbox"
        className="peer sr-only"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="mt-px rounded-[var(--radius-ctl)] peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-focus-ring group-hover:[&>span]:border-line-strong">
        <CheckboxBox checked={checked} disabled={disabled} />
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span
          className={cn(
            "flex items-center gap-2 text-[13px] text-text-primary",
            (!checked || disabled) && "text-text-secondary",
            disabled && "text-text-tertiary",
          )}
        >
          <span className="min-w-0 flex-1">{children}</span>
          {trailing}
        </span>
        {description ? <span className="text-[12px] text-text-tertiary">{description}</span> : null}
      </span>
    </label>
  );
}
