"use client";

import type { MapModeId } from "@/config/layers";
import { type BasemapId, useMapLayersStore } from "@/state/map-layers-store";
import { Button } from "@/ui/button";
import { cn } from "@/ui/cn";
import { type SegmentOption, Segmented } from "@/ui/segmented";
import { GroupSection } from "./group-section";
import { LegendNote } from "./layer-legend";
import type { RowDensity } from "./layer-row";

const BASEMAP_OPTIONS: readonly SegmentOption<BasemapId>[] = [
  { value: "s2-mosaic", label: "Мозаика S2" },
  { value: "chart", label: "Карта" },
  { value: "bathymetry", label: "Рельеф дна" },
];

const BASEMAP_SOURCE: Record<BasemapId, string> = {
  "s2-mosaic": "Безоблачная мозаика Sentinel-2 за 2025 год · 10\u202Fм · не снимок конкретной даты",
  chart: "Векторная карта OpenStreetMap",
  bathymetry: "Рельеф суши и дна, до масштаба z8",
};

export const BASEMAP_SHORT: Record<BasemapId, string> = {
  "s2-mosaic": "мозаика EOX 2025",
  chart: "карта OpenStreetMap",
  bathymetry: "рельеф NASA GIBS",
};

function PlanningSuggestion() {
  const setBasemap = useMapLayersStore((state) => state.setBasemap);
  return (
    <div className="flex items-center gap-2 pt-1">
      <span className="min-w-0 flex-1 text-[12px] leading-4 text-text-secondary">
        Для планирования удобнее «Карта»
      </span>
      <Button size="sm" onClick={() => setBasemap("chart")}>
        Переключить
      </Button>
    </div>
  );
}

export function BasemapGroup({ mode, density }: { mode: MapModeId; density: RowDensity }) {
  const basemapId = useMapLayersStore((state) => state.basemapId);
  const setBasemap = useMapLayersStore((state) => state.setBasemap);
  const current = BASEMAP_OPTIONS.find((option) => option.value === basemapId);

  return (
    <GroupSection
      mode={mode}
      id="basemap"
      title="Подложка"
      density={density}
      summary={current?.label}
    >
      <div className="flex flex-col gap-1.5 pt-1">
        <Segmented
          label="Подложка"
          value={basemapId}
          options={BASEMAP_OPTIONS}
          onChange={setBasemap}
          stretch
          size={density === "touch" ? "md" : "sm"}
          className={cn(density === "touch" && "[&>button]:h-10")}
        />
        <LegendNote tone="source">{BASEMAP_SOURCE[basemapId]}</LegendNote>
        {mode === "survey" && basemapId !== "chart" ? <PlanningSuggestion /> : null}
      </div>
    </GroupSection>
  );
}
