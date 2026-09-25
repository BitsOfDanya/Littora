import type { ReactNode } from "react";
import { cn } from "@/ui/cn";

export function ReadoutGrid({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("grid grid-cols-2 border-t border-l border-line-hairline", className)}>
      {children}
    </div>
  );
}

type ReadoutProps = {
  label: ReactNode;
  value: ReactNode;
  unit?: ReactNode;
  interval?: ReactNode;
  note?: ReactNode;
  glyph?: ReactNode;
  valueFont?: "mono" | "sans";
  tone?: "primary" | "secondary";
};

export function Readout({
  label,
  value,
  unit,
  interval,
  note,
  glyph,
  valueFont = "mono",
  tone = "primary",
}: ReadoutProps) {
  return (
    <div className="@container flex min-h-[76px] min-w-0 flex-col gap-0.5 border-r border-b border-line-hairline px-3 py-2">
      <span className="text-[12px] leading-4 text-text-secondary">{label}</span>
      <span className="flex min-w-0 flex-wrap items-baseline gap-x-1.5">
        {glyph ? <span className="self-center">{glyph}</span> : null}
        <span
          className={cn(
            "whitespace-nowrap",
            valueFont === "mono"
              ? "font-mono text-[17px] leading-6 font-medium @[150px]:text-[20px]"
              : "text-[15px] leading-6 font-semibold",
            tone === "primary" ? "text-text-primary" : "text-text-secondary",
          )}
        >
          {value}
        </span>
        {unit ? <span className="text-[12px] text-text-secondary">{unit}</span> : null}
      </span>
      {interval ? (
        <span className="font-mono text-[11px] leading-[14px] text-text-secondary">{interval}</span>
      ) : null}
      {note ? <span className="text-[11px] leading-[14px] text-text-tertiary">{note}</span> : null}
    </div>
  );
}
