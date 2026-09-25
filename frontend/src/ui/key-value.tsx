import type { ReactNode } from "react";
import { cn } from "./cn";

export function KeyValueList({ children, className }: { children: ReactNode; className?: string }) {
  return <dl className={cn("flex flex-col", className)}>{children}</dl>;
}

type KeyValueProps = {
  label: ReactNode;
  children: ReactNode;
  unit?: ReactNode;
  hint?: ReactNode;
  tag?: ReactNode;
};

export function KeyValue({ label, children, unit, hint, tag }: KeyValueProps) {
  return (
    <div className="flex min-h-7 items-baseline gap-3 border-b border-line-hairline py-1 last:border-b-0">
      <dt className="flex min-w-0 flex-1 items-center gap-1.5 text-[12px] text-text-secondary">
        {label}
        {tag}
      </dt>
      <dd className="flex flex-wrap items-baseline justify-end gap-x-1 text-right font-mono text-[13px] font-medium text-text-primary">
        {children}
        {unit ? (
          <span className="font-sans text-[12px] font-normal text-text-tertiary">{unit}</span>
        ) : null}
        {hint ? <span className="text-[11px] font-normal text-text-tertiary">{hint}</span> : null}
      </dd>
    </div>
  );
}
