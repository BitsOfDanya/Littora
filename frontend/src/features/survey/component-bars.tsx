import type { SurveyComponents } from "@/data/survey";
import { formatNumber } from "@/lib/format/numbers";
import { cn } from "@/ui/cn";
import { SCORE_COMPONENTS } from "./plan-model";
import { COMPONENT_LABELS, NOT_ASSESSED } from "./survey-copy";

function componentText(value: number | undefined): string {
  return value === undefined ? NOT_ASSESSED : formatNumber(value, 2);
}

export function componentsAriaLabel(components: SurveyComponents): string {
  return SCORE_COMPONENTS.map(
    (key) => `${COMPONENT_LABELS[key].full} ${componentText(components[key])}`,
  ).join(", ");
}

export function ComponentBars({ components }: { components: SurveyComponents }) {
  return (
    <div className="grid grid-cols-6 gap-2" aria-hidden>
      {SCORE_COMPONENTS.map((key) => {
        const value = components[key];
        return (
          <span
            key={key}
            className="group/bar relative flex flex-col gap-1"
            title={`${COMPONENT_LABELS[key].full} ${componentText(value)}`}
          >
            <span
              className={cn(
                "block h-1.5 w-full bg-surface-sunken",
                value === undefined && "border border-dashed border-line-control bg-transparent",
              )}
            >
              {value === undefined ? null : (
                <span
                  className="block h-full bg-text-primary"
                  style={{ width: `${Math.round(value * 100)}%` }}
                />
              )}
            </span>
            <span className="text-[11px] leading-3 text-text-tertiary">
              {COMPONENT_LABELS[key].short}
            </span>
          </span>
        );
      })}
    </div>
  );
}
