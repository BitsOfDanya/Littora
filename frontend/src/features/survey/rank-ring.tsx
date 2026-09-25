import { cn } from "@/ui/cn";

export function RankRing({
  rank,
  selected,
  size = 22,
}: {
  rank: number;
  selected?: boolean;
  size?: number;
}) {
  return (
    <span
      aria-hidden
      style={{ width: size, height: size }}
      className={cn(
        "grid shrink-0 place-items-center rounded-full border-[2.2px] border-accent-selection font-mono text-[12px] font-semibold",
        selected
          ? "bg-accent-selection text-surface-panel"
          : "bg-surface-panel text-accent-selection",
      )}
    >
      {rank}
    </span>
  );
}
