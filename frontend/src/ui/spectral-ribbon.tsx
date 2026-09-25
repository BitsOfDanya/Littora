import { SENTINEL2_BANDS, type Sentinel2BandId } from "@/domain/sentinel2";
import { cn } from "./cn";

export type BandTint = "r" | "g" | "b" | "index";

const HEIGHT_BY_RESOLUTION: Record<number, number> = { 10: 1, 20: 2 / 3, 60: 5 / 12 };

const TINT_CLASS: Record<BandTint, string> = {
  r: "bg-[#E0776B] day:bg-[#B8473D]",
  g: "bg-[#62B884] day:bg-[#2F8A57]",
  b: "bg-[#6A9BE6] day:bg-[#2F66C2]",
  index: "bg-[#E4E9EB] day:bg-[#111416]",
};

type SpectralRibbonProps = {
  size?: "sm" | "lg";
  lit?: Partial<Record<Sentinel2BandId, BandTint>>;
  baseClassName?: string;
  className?: string;
  showTitles?: boolean;
};

export function SpectralRibbon({
  size = "sm",
  lit = {},
  baseClassName = "bg-text-tertiary/50",
  className,
  showTitles = true,
}: SpectralRibbonProps) {
  const cellWidth = size === "sm" ? 4 : 6;
  const height = size === "sm" ? 12 : 18;
  return (
    <span
      className={cn("inline-flex items-end gap-px", className)}
      style={{ height }}
      aria-hidden={!showTitles}
    >
      {SENTINEL2_BANDS.map((band) => {
        const tint = lit[band.id];
        const isCirrus = band.id === "B10";
        return (
          <span
            key={band.id}
            title={
              showTitles
                ? `${band.id} · ${band.centralWavelengthNm} нм · ${band.resolutionM} м · ${band.name}`
                : undefined
            }
            style={{
              width: cellWidth,
              height: Math.round(height * HEIGHT_BY_RESOLUTION[band.resolutionM]),
            }}
            className={cn(
              "block",
              isCirrus
                ? "border border-dotted border-text-tertiary bg-transparent"
                : tint
                  ? TINT_CLASS[tint]
                  : baseClassName,
            )}
          />
        );
      })}
    </span>
  );
}
