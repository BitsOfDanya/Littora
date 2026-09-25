import type { StepRamp } from "@/features/map/color";
import { formatNumber, formatSigned } from "@/lib/format/numbers";
import { cn } from "@/ui/cn";

const NNBSP = " ";

export function coverageTicks(ramp: StepRamp): string[] {
  const last = ramp.stops.length - 1;
  return ramp.stops.map((stop, index) => {
    const percent = formatNumber(stop * 100);
    return index === last ? `≥${percent}${NNBSP}%` : percent;
  });
}

export function coverageRangeLabel(ramp: StepRamp): string {
  const ticks = coverageTicks(ramp);
  return `${ticks[0]}–${ticks.at(-1)}`;
}

function RampBlocks({ ramp, className }: { ramp: StepRamp; className?: string }) {
  return (
    <span aria-hidden className={cn("flex border border-line-control", className)}>
      {ramp.colors.map((color) => (
        <span key={color} className="min-w-0 flex-1" style={{ backgroundColor: color }} />
      ))}
    </span>
  );
}

export function LegendRamp({
  ramp,
  ticks,
  label,
}: {
  ramp: StepRamp;
  ticks: readonly string[];
  label: string;
}) {
  return (
    <div role="img" aria-label={`${label}: ${ticks.join(", ")}`} className="flex flex-col gap-0.5">
      <RampBlocks ramp={ramp} className="h-2" />
      <span
        aria-hidden
        className="grid font-mono text-[10.5px] leading-3 font-medium text-text-tertiary"
        style={{ gridTemplateColumns: `repeat(${ramp.colors.length}, minmax(0, 1fr))` }}
      >
        {ticks.map((tick) => (
          <span key={tick} className="whitespace-nowrap">
            {tick}
          </span>
        ))}
      </span>
    </div>
  );
}

export function DivergingLegend({
  ramp,
  limit,
  unit,
  label,
}: {
  ramp: StepRamp;
  limit: number;
  unit: string;
  label: string;
}) {
  const ticks = [formatSigned(-limit), "0", `${formatSigned(limit)}${NNBSP}${unit}`];
  return (
    <div role="img" aria-label={`${label}: ${ticks.join(" … ")}`} className="flex flex-col gap-0.5">
      <RampBlocks ramp={ramp} className="h-2" />
      <span
        aria-hidden
        className="flex justify-between font-mono text-[10.5px] leading-3 font-medium text-text-tertiary"
      >
        {ticks.map((tick) => (
          <span key={tick}>{tick}</span>
        ))}
      </span>
    </div>
  );
}

export function MiniRamp({ ramp }: { ramp: StepRamp }) {
  return <RampBlocks ramp={ramp} className="h-[7px] w-12" />;
}
