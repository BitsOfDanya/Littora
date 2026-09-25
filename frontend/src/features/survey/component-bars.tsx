import type { SurveyScoreComponent } from "@/domain/survey";
import { formatNumber } from "@/lib/format/numbers";
import { SCORE_COMPONENTS } from "./plan-model";
import { COMPONENT_LABELS } from "./survey-copy";

export function componentsAriaLabel(
  components: Readonly<Record<SurveyScoreComponent, number>>,
): string {
  return SCORE_COMPONENTS.map(
    (key) => `${COMPONENT_LABELS[key].full} ${formatNumber(components[key], 2)}`,
  ).join(", ");
}

export function ComponentBars({
  components,
}: {
  components: Readonly<Record<SurveyScoreComponent, number>>;
}) {
  return (
    <div className="grid grid-cols-6 gap-2" aria-hidden>
      {SCORE_COMPONENTS.map((key) => (
        <span
          key={key}
          className="group/bar relative flex flex-col gap-1"
          title={`${COMPONENT_LABELS[key].full} ${formatNumber(components[key], 2)}`}
        >
          <span className="block h-1.5 w-full bg-surface-sunken">
            <span
              className="block h-full bg-text-primary"
              style={{ width: `${Math.round(components[key] * 100)}%` }}
            />
          </span>
          <span className="text-[11px] leading-3 text-text-tertiary">
            {COMPONENT_LABELS[key].short}
          </span>
        </span>
      ))}
    </div>
  );
}
