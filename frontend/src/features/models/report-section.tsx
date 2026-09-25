import type { ReactNode } from "react";
import { cn } from "@/ui/cn";
import { SECTION_COPY, type SectionId } from "./copy";
import styles from "./report.module.css";

type ReportSectionProps = {
  id: SectionId;
  index: number;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
};

export const sectionDomId = (id: SectionId) => `models-${id}`;

export function ReportSection({ id, index, aside, children, className }: ReportSectionProps) {
  const domId = sectionDomId(id);
  const copy = SECTION_COPY[id];
  return (
    <section
      id={domId}
      aria-labelledby={`${domId}-title`}
      className={cn("border-t border-line-hairline px-4 py-7 @2xl:px-8 @2xl:py-8", className)}
    >
      <header className="mb-5 grid grid-cols-12 gap-x-6">
        <div className="col-span-12 flex items-baseline gap-3 @4xl:col-span-10">
          <span aria-hidden className="w-3 shrink-0 font-mono text-[11px] text-text-tertiary">
            {index}
          </span>
          <div className="flex min-w-0 flex-col gap-1.5">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <h2
                id={`${domId}-title`}
                className={cn(
                  "font-serif text-[22px] leading-[28px] font-normal text-text-primary not-italic",
                  styles.h2,
                )}
              >
                {copy.title}
              </h2>
              {aside}
            </div>
            <p className="max-w-[70ch] text-[13px] leading-5 text-text-secondary">{copy.lede}</p>
          </div>
        </div>
      </header>
      {children}
    </section>
  );
}
