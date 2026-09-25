import type { Interval } from "@/data/models";
import { cn } from "@/ui/cn";

const WIDTH = 56;

const at = (value: number) => Math.round(Math.min(1, Math.max(0, value)) * WIDTH);

export function MetricBar({
  value,
  interval,
  emphasis,
}: {
  value: number | null;
  interval: Interval | null;
  emphasis?: boolean;
}) {
  const low = interval ? at(interval[0]) + 0.5 : 0;
  const high = interval ? at(interval[1]) - 0.5 : 0;
  return (
    <svg
      width={WIDTH}
      height={10}
      viewBox={`0 0 ${WIDTH} 10`}
      aria-hidden
      focusable={false}
      className="shrink-0"
    >
      <rect x={0} y={0} width={WIDTH} height={5} className="fill-line-hairline" />
      {value !== null ? (
        <rect
          x={0}
          y={0}
          width={at(value)}
          height={5}
          className={cn(emphasis ? "fill-text-primary" : "fill-text-secondary")}
        />
      ) : null}
      {interval ? (
        <path
          d={`M${low} 8.5H${high}M${low} 6.5V10M${high} 6.5V10`}
          className="stroke-text-tertiary"
          strokeWidth={1}
          fill="none"
        />
      ) : null}
    </svg>
  );
}
