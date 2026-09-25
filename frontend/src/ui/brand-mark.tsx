import { SENTINEL2_BANDS } from "@/domain/sentinel2";
import { cn } from "./cn";

const HEIGHT_BY_RESOLUTION: Record<number, number> = { 10: 1, 20: 2 / 3, 60: 5 / 12 };

export function BrandMark({ height = 16, className }: { height?: number; className?: string }) {
  const barWidth = Math.max(1.5, height / 7);
  const gap = Math.max(1, height / 16);
  const width = SENTINEL2_BANDS.length * barWidth + (SENTINEL2_BANDS.length - 1) * gap;
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden
      focusable={false}
      className={cn("shrink-0", className)}
    >
      {SENTINEL2_BANDS.map((band, index) => {
        const barHeight = height * HEIGHT_BY_RESOLUTION[band.resolutionM];
        const x = index * (barWidth + gap);
        return band.id === "B10" ? (
          <rect
            key={band.id}
            x={x + 0.35}
            y={height - barHeight + 0.35}
            width={barWidth - 0.7}
            height={barHeight - 0.7}
            fill="none"
            stroke="currentColor"
            strokeWidth={0.7}
            strokeDasharray="1 1"
          />
        ) : (
          <rect
            key={band.id}
            x={x}
            y={height - barHeight}
            width={barWidth}
            height={barHeight}
            fill="currentColor"
          />
        );
      })}
    </svg>
  );
}
