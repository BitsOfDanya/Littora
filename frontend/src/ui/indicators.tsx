import type { ConfidenceClass, SurveyPriority } from "@/domain/detection";
import { cn } from "./cn";
import { IconAlarm, IconCaution, IconDiamond } from "./icons";

export type Severity = "alarm" | "caution" | "info";

const SEVERITY_WORD: Record<Severity, string> = {
  alarm: "Тревога",
  caution: "Внимание",
  info: "Сведения",
};

export function SeverityGlyph({
  severity,
  acknowledged,
  size = 14,
  withWord,
  className,
}: {
  severity: Severity;
  acknowledged?: boolean;
  size?: number;
  withWord?: boolean;
  className?: string;
}) {
  const Glyph =
    severity === "alarm" ? IconAlarm : severity === "caution" ? IconCaution : IconDiamond;
  const tone =
    severity === "alarm"
      ? "text-state-alarm"
      : severity === "caution"
        ? "text-state-caution"
        : "text-state-info";
  return (
    <span className={cn("inline-flex items-center gap-1", tone, className)}>
      <Glyph
        size={size}
        fill={acknowledged ? "none" : "currentColor"}
        fillOpacity={acknowledged ? 0 : 0.28}
      />
      {withWord ? <span className="text-[12px]">{SEVERITY_WORD[severity]}</span> : null}
    </span>
  );
}

const CONFIDENCE_DASH: Record<ConfidenceClass, string | undefined> = {
  likely: undefined,
  possible: "4 2.5",
  low: "0.6 1.8",
};
export const CONFIDENCE_WORD: Record<ConfidenceClass, string> = {
  likely: "высокая",
  possible: "средняя",
  low: "низкая",
};

export function ConfidenceGlyph({
  confidence,
  score,
  withWord = true,
}: {
  confidence: ConfidenceClass;
  score?: number;
  withWord?: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <svg width="16" height="6" aria-hidden className="shrink-0 text-text-primary">
        <line
          x1="0"
          x2="16"
          y1="3"
          y2="3"
          stroke="currentColor"
          strokeWidth={confidence === "likely" ? 1.6 : 1.4}
          strokeDasharray={CONFIDENCE_DASH[confidence]}
        />
      </svg>
      {withWord ? <span>{CONFIDENCE_WORD[confidence]}</span> : null}
      {score !== undefined ? (
        <span className="font-mono text-text-secondary">{score.toFixed(2).replace(".", ",")}</span>
      ) : null}
    </span>
  );
}

const PRIORITY_LEVEL: Record<SurveyPriority, number> = { high: 3, medium: 2, low: 1 };
export const PRIORITY_WORD: Record<SurveyPriority, string> = {
  high: "Высокий",
  medium: "Средний",
  low: "Низкий",
};

export function PriorityBars({
  priority,
  withWord,
}: {
  priority: SurveyPriority;
  withWord?: boolean;
}) {
  const level = PRIORITY_LEVEL[priority];
  return (
    <span
      className="inline-flex items-center gap-1.5"
      title={`Приоритет: ${PRIORITY_WORD[priority].toLowerCase()}`}
    >
      <span className="inline-flex items-end gap-px" aria-hidden>
        {[1, 2, 3].map((step) => (
          <span
            key={step}
            className={cn(
              "block h-2.5 w-[3px] border border-text-primary",
              step <= level ? "bg-text-primary" : "bg-transparent",
            )}
          />
        ))}
      </span>
      {withWord ? <span>{PRIORITY_WORD[priority]}</span> : null}
    </span>
  );
}
