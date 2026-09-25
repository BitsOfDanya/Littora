import { Fragment } from "react";
import { cn } from "@/ui/cn";

export type Crumb = { label: string; onSelect?: () => void; serif?: boolean };

export function Breadcrumbs({
  crumbs,
  className,
}: {
  crumbs: readonly Crumb[];
  className?: string;
}) {
  return (
    <nav
      aria-label="Путь"
      className={cn(
        "flex min-w-0 flex-wrap items-center gap-x-1.5 text-[12px] text-text-secondary",
        className,
      )}
    >
      {crumbs.map((crumb, index) => (
        <Fragment key={`${crumb.label}-${index}`}>
          {index > 0 ? (
            <span aria-hidden className="text-text-tertiary">
              ›
            </span>
          ) : null}
          <button
            type="button"
            onClick={crumb.onSelect}
            disabled={!crumb.onSelect}
            aria-current={index === crumbs.length - 1 ? "location" : undefined}
            className={cn(
              "rounded-[var(--radius-ctl)] px-0.5 hover:text-text-primary hover:underline disabled:cursor-default disabled:no-underline disabled:hover:text-text-secondary",
              crumb.serif && "font-serif text-[13px] italic",
              index === crumbs.length - 1 && "text-text-primary",
            )}
          >
            {crumb.label}
          </button>
        </Fragment>
      ))}
    </nav>
  );
}
