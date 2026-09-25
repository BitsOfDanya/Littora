"use client";

import type { ReactNode } from "react";
import type { MapModeId } from "@/config/layers";
import { useCartoucheStore } from "@/state/cartouche-store";
import { Button } from "@/ui/button";
import { cn } from "@/ui/cn";
import type { RowDensity } from "./layer-row";
import { useLayerCounts } from "./use-layer-counts";

export function FooterBar({ children, density }: { children: ReactNode; density: RowDensity }) {
  return (
    <div
      className={cn(
        "flex shrink-0 flex-wrap items-center gap-x-2 gap-y-1 border-t border-line-hairline px-3",
        density === "touch" ? "min-h-14 py-2" : "min-h-8",
      )}
    >
      {children}
    </div>
  );
}

export function LegendFooter({
  mode,
  density,
  lead,
}: {
  mode: MapModeId;
  density: RowDensity;
  lead?: ReactNode;
}) {
  const { off, planned } = useLayerCounts(mode);
  const showAll = useCartoucheStore((state) => state.showAllLayers);
  const toggleShowAll = useCartoucheStore((state) => state.toggleShowAllLayers);
  return (
    <FooterBar density={density}>
      {lead}
      <span className="min-w-0 flex-1 text-[11px] text-text-tertiary">
        Выключено: <span className="font-mono text-text-secondary">{off}</span> · в плане:{" "}
        <span className="font-mono text-text-secondary">{planned}</span>
      </span>
      <Button
        size="sm"
        aria-pressed={showAll}
        title={showAll ? "Показать только слои режима" : "Показать все слои, включая плановые"}
        onClick={toggleShowAll}
        className={cn(
          density === "touch" && "h-10 px-3",
          showAll && "font-semibold shadow-[inset_0_0_0_1px_var(--text-primary)]",
        )}
      >
        Все слои
      </Button>
    </FooterBar>
  );
}
