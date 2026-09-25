"use client";

import type { ReactNode } from "react";
import type { LayerDefinition } from "@/config/layers";
import { useLayerLoadState, useLayerVisible, useMapLayersStore } from "@/state/map-layers-store";
import { Button } from "@/ui/button";
import { CheckboxBox } from "@/ui/checkbox";
import { cn } from "@/ui/cn";
import { DemoTag } from "@/ui/demo-mark";
import { SeverityGlyph } from "@/ui/indicators";
import { PlannedTag } from "@/ui/planned";
import { LegendNote } from "./layer-legend";
import type { LayerTruth } from "./use-layer-truth";

export type RowDensity = "compact" | "touch";

type LayerRowProps = {
  layer: LayerDefinition;
  truth: LayerTruth;
  label?: string;
  showDemoTag?: boolean;
  description?: ReactNode;
  trailing?: ReactNode;
  legend?: ReactNode;
  source?: string;
  forceLegend?: boolean;
  density?: RowDensity;
};

function LoadingLine() {
  return (
    <div className="flex flex-col gap-1" aria-live="polite">
      <LegendNote tone="source">загрузка тайлов…</LegendNote>
      <span aria-hidden className="block h-0.5 w-full animate-pulse bg-text-tertiary" />
    </div>
  );
}

function ErrorLine({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex items-center gap-2 text-[12px] text-state-alarm" role="status">
      <SeverityGlyph severity="alarm" size={12} />
      <span>тайлы недоступны</span>
      <Button size="sm" onClick={onRetry}>
        Повторить
      </Button>
    </div>
  );
}

export function LayerRow({
  layer,
  truth,
  label,
  showDemoTag,
  description,
  trailing,
  legend,
  source,
  forceLegend,
  density = "compact",
}: LayerRowProps) {
  const visible = useLayerVisible(layer.id);
  const loadState = useLayerLoadState(layer.id);
  const toggleLayer = useMapLayersStore((state) => state.toggleLayer);
  const retryLayer = useMapLayersStore((state) => state.retryLayer);
  const planned = truth === "planned";
  const checked = !planned && visible;
  const showLegend = legend && (checked || forceLegend);
  const reason = planned ? layer.plannedReason : undefined;
  const details = description || reason || showLegend || (checked && loadState);

  return (
    <div className="flex flex-col">
      <div className={cn("flex items-center gap-2", density === "touch" ? "min-h-10" : "min-h-7")}>
        <label
          className={cn(
            "group flex min-w-0 flex-1 cursor-pointer items-center gap-2.5 self-stretch",
            planned && "cursor-not-allowed",
          )}
        >
          <input
            type="checkbox"
            className="peer sr-only"
            checked={checked}
            disabled={planned}
            onChange={() => toggleLayer(layer.id)}
          />
          <span className="rounded-[var(--radius-ctl)] peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-focus-ring group-hover:[&>span]:border-line-strong">
            <CheckboxBox checked={checked} disabled={planned} />
          </span>
          <span
            className={cn(
              "min-w-0 flex-1 text-[13px] leading-4",
              checked ? "text-text-primary" : "text-text-tertiary",
            )}
          >
            {label ?? layer.label}
          </span>
        </label>
        {planned && layer.capability ? <PlannedTag capability={layer.capability} /> : null}
        {showDemoTag && truth === "demo" ? <DemoTag /> : null}
        {trailing}
      </div>
      {details ? (
        <div className="flex flex-col gap-1.5 pb-2 pl-[26px]">
          {description ? <LegendNote>{description}</LegendNote> : null}
          {reason ? <LegendNote tone="source">{reason}</LegendNote> : null}
          {showLegend ? legend : null}
          {checked && loadState === "loading" ? <LoadingLine /> : null}
          {checked && loadState === "error" ? (
            <ErrorLine onRetry={() => retryLayer(layer.id)} />
          ) : null}
          {showLegend && source && !loadState ? (
            <LegendNote tone="source">{source}</LegendNote>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
