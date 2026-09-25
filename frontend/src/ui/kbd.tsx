import type { ReactNode } from "react";
import { cn } from "./cn";

export function Kbd({
  children,
  inverted,
  className,
}: {
  children: ReactNode;
  inverted?: boolean;
  className?: string;
}) {
  return (
    <kbd
      className={cn(
        "inline-grid h-[18px] min-w-[18px] place-items-center rounded-[var(--radius-ctl)] border border-b-2 border-line-control px-1 font-mono text-[11px] leading-none text-text-secondary",
        inverted && "border-primary-fill bg-primary-fill text-primary-text",
        className,
      )}
    >
      {children}
    </kbd>
  );
}
