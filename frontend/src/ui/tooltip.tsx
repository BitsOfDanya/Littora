import type { ReactNode } from "react";
import { cn } from "./cn";

type TooltipSide = "top" | "bottom" | "left" | "right";

const SIDES: Record<TooltipSide, string> = {
  top: "bottom-full left-1/2 mb-1.5 -translate-x-1/2",
  bottom: "top-full left-1/2 mt-1.5 -translate-x-1/2",
  left: "right-full top-1/2 mr-1.5 -translate-y-1/2",
  right: "left-full top-1/2 ml-1.5 -translate-y-1/2",
};

export function Tooltip({
  content,
  shortcut,
  side = "bottom",
  children,
  className,
}: {
  content: ReactNode;
  shortcut?: string;
  side?: TooltipSide;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span className={cn("group/tooltip relative inline-flex", className)}>
      {children}
      <span
        role="tooltip"
        className={cn(
          "pointer-events-none absolute z-50 flex w-max max-w-72 items-center gap-2 rounded-[var(--radius-ctl)] bg-primary-fill px-2 py-1 text-[12px] leading-4 text-primary-text opacity-0 transition-opacity duration-[var(--t-2)]",
          "group-hover/tooltip:opacity-100 group-hover/tooltip:delay-[400ms] group-has-[:focus-visible]/tooltip:opacity-100 group-has-[:focus-visible]/tooltip:delay-0",
          SIDES[side],
        )}
      >
        {content}
        {shortcut ? (
          <kbd className="rounded-[var(--radius-ctl)] border border-primary-text/40 px-1 font-mono text-[11px]">
            {shortcut}
          </kbd>
        ) : null}
      </span>
    </span>
  );
}
