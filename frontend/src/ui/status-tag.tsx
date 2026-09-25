import type { ReactNode } from "react";
import { cn } from "./cn";

export type StatusTone = "neutral" | "selection" | "caution" | "alarm" | "ok" | "info";

const TONES: Record<StatusTone, string> = {
  neutral: "bg-surface-sunken text-text-secondary",
  selection: "bg-accent-selection-wash text-accent-selection",
  caution: "bg-state-caution-wash text-state-caution",
  alarm: "bg-state-alarm-wash text-state-alarm",
  ok: "bg-state-ok-wash text-state-ok",
  info: "bg-surface-sunken text-state-info",
};

export function StatusTag({
  tone = "neutral",
  glyph,
  children,
  className,
  title,
}: {
  tone?: StatusTone;
  glyph?: ReactNode;
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex h-[22px] items-center gap-1.5 rounded-[var(--radius-ctl)] px-2 text-[12px] whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {glyph}
      {children}
    </span>
  );
}
