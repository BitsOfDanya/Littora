"use client";

import { ATTRIBUTIONS, type AttributionId, findBasemap } from "@/config/basemaps";
import { useMapLayersStore } from "@/state/map-layers-store";
import { Caps } from "@/ui/section";
import { StatusPopover } from "./status-popover";

const SOURCE_ENTRIES: readonly { title: string; source: AttributionId }[] = [
  { title: "Мозаика Sentinel-2", source: "eox" },
  { title: "Векторная карта", source: "openFreeMap" },
  { title: "Рельеф суши и дна", source: "gibs" },
];

export function SourcesItem() {
  const compact = findBasemap(useMapLayersStore((state) => state.basemapId)).attribution;
  return (
    <StatusPopover
      title="Источники подложек"
      align="right"
      width="w-[380px]"
      triggerLabel={`Источники: ${compact}`}
      trigger={
        <>
          <span className="2xl:hidden">Источники</span>
          <span className="hidden 2xl:inline">{compact}</span>
        </>
      }
    >
      <div className="flex flex-col gap-2.5 px-3 py-3">
        <Caps>Источники подложек</Caps>
        <ul className="flex flex-col gap-2.5">
          {SOURCE_ENTRIES.map((entry) => (
            <li key={entry.source} className="flex flex-col gap-0.5">
              <span className="text-[12px] font-semibold text-text-primary">{entry.title}</span>
              <span className="text-[12px] leading-4 text-text-secondary">
                {ATTRIBUTIONS[entry.source]}
              </span>
            </li>
          ))}
        </ul>
        <p className="border-t border-line-hairline pt-2 font-mono text-[11px] text-text-tertiary">
          WGS 84 · EPSG:3857 · время UTC
        </p>
      </div>
    </StatusPopover>
  );
}
