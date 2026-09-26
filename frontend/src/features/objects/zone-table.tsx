"use client";

import { useMemo } from "react";
import { FLAG_SHORT, type RealZone, zoneColor } from "@/features/analysis/zones";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { formatLngLat } from "@/lib/format/coordinates";
import { formatArea, formatNumber } from "@/lib/format/numbers";
import { cn } from "@/ui/cn";
import { pluralRu } from "./plural";
import type { TableDensity } from "./object-table";
import { useInViewCount } from "./use-in-view-count";

const HEADER_CELL =
  "sticky top-0 z-[1] h-7 border-b border-line-hairline bg-surface-panel px-1 text-left text-[11px] font-semibold whitespace-nowrap text-text-tertiary";
const CELL = "px-1 whitespace-nowrap";
const NNBSP = " ";

const probability = (value: number | null) => (value === null ? "—" : formatNumber(value, 2));

function rowLabel(zone: RealZone): string {
  const center = zone.centroid ? `, центр ${formatLngLat(zone.centroid)}` : "";
  const area = zone.areaM2 === null ? "" : `, площадь ${formatArea(zone.areaM2)}`;
  const flags = zone.flags.length ? `, ${zone.flags.map((flag) => flag.label).join(", ")}` : "";
  return `${zone.id}, вероятность макс. ${probability(zone.probabilityMax)}, средняя ${probability(zone.probabilityMean)}${area}${center}${flags}`;
}

export function ZoneTable({
  zones,
  threshold,
  selectedId,
  onSelect,
  density = "compact",
}: {
  zones: readonly RealZone[];
  threshold: number | null;
  selectedId: string | null;
  onSelect: (zone: RealZone) => void;
  density?: TableDensity;
}) {
  const setHint = useStatusHintStore((state) => state.setHint);
  return (
    <table
      role="grid"
      aria-label="Объекты: зоны детектора по вероятности"
      aria-readonly
      className="w-full border-collapse"
    >
      <thead>
        <tr>
          <th scope="col" className={cn(HEADER_CELL, "pl-2")}>
            Зона
          </th>
          <th scope="col" className={cn(HEADER_CELL, "text-right")} title="Вероятность, максимум">
            p макс.
          </th>
          <th scope="col" className={cn(HEADER_CELL, "text-right")} title="Вероятность, средняя">
            p ср.
          </th>
          <th scope="col" className={cn(HEADER_CELL, "text-right")} title="Пикселей 10 м">
            Пикс.
          </th>
          <th scope="col" className={cn(HEADER_CELL, "pr-2 text-right")} title="Площадь зоны">
            Площадь
          </th>
        </tr>
      </thead>
      <tbody>
        {zones.map((zone) => {
          const selected = zone.id === selectedId;
          const [red, green, blue] = zoneColor(zone.probabilityMax, threshold);
          return (
            <tr
              key={zone.id}
              tabIndex={0}
              aria-selected={selected}
              aria-label={rowLabel(zone)}
              onClick={() => onSelect(zone)}
              onKeyDown={(event) => {
                if (event.key !== "Enter") return;
                event.preventDefault();
                onSelect(zone);
              }}
              onMouseEnter={() => setHint(`${zone.id} — щелчок: открыть досье зоны`)}
              onMouseLeave={() => setHint(null)}
              className={cn(
                "cursor-pointer text-[12px] text-text-primary transition-colors duration-[var(--t-2)] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus-ring",
                density === "touch" ? "h-10" : "h-7",
                selected
                  ? "bg-accent-selection-wash [&>td:first-child]:shadow-[inset_3px_0_0_var(--accent-selection)]"
                  : "hover:bg-surface-raised",
              )}
            >
              <td
                className={cn(
                  CELL,
                  "pl-2 font-mono font-medium",
                  selected && "text-accent-selection",
                )}
              >
                <span className="inline-flex items-center gap-1.5">
                  <span
                    aria-hidden
                    className="size-2.5 rounded-[1px] border border-line-hairline"
                    style={{ background: `rgb(${red},${green},${blue})` }}
                  />
                  {zone.id}
                  {zone.flags.map((flag) => (
                    <span
                      key={flag.kind}
                      title={[flag.label, ...flag.evidence].join(" · ")}
                      className="rounded-[2px] border border-line-hairline px-1 font-sans text-[10px] leading-[14px] font-normal text-text-secondary"
                    >
                      {FLAG_SHORT[flag.kind] ?? flag.label}
                    </span>
                  ))}
                </span>
              </td>
              <td className={cn(CELL, "text-right font-mono")}>
                {probability(zone.probabilityMax)}
              </td>
              <td className={cn(CELL, "text-right font-mono text-text-secondary")}>
                {probability(zone.probabilityMean)}
              </td>
              <td className={cn(CELL, "text-right font-mono text-text-secondary")}>
                {zone.pixels === null ? "—" : formatNumber(zone.pixels)}
              </td>
              <td className={cn(CELL, "pr-2 text-right font-mono")}>
                {zone.areaM2 === null ? "—" : formatArea(zone.areaM2)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function ZonesSummary({ zones }: { zones: readonly RealZone[] }) {
  const centroids = useMemo(
    () => zones.flatMap((zone) => (zone.centroid ? [zone.centroid] : [])),
    [zones],
  );
  const inView = useInViewCount(centroids);
  const areaM2 = zones.reduce((sum, zone) => sum + (zone.areaM2 ?? 0), 0);
  const count = zones.length;
  return (
    <span className="font-mono text-[11px] text-text-secondary">
      {count} {pluralRu(count, ["зона", "зоны", "зон"])} · {formatArea(areaM2).replace(" ", NNBSP)}{" "}
      · в кадре {inView ?? "—"}
    </span>
  );
}
