"use client";

import type { CSSProperties } from "react";
import { findBasemap } from "@/config/basemaps";
import { formatNumber } from "@/lib/format/numbers";
import { useMapLayersStore } from "@/state/map-layers-store";
import { cn } from "@/ui/cn";
import { useMapViewStore } from "../state/map-view-store";

const NICE_LENGTHS = [0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000] as const;
const METERS_PER_KM = 1000;
const METERS_PER_NM = 1852;
const KM_MAX_PX = 170;
const NM_MAX_PX = 128;
const CHAR_WIDTH_PX = 6.6;
const BAR_HEIGHT_PX = 4;
const SVG_WIDTH_PX = 200;

type ScaleLength = { value: number; px: number; segments: number };

function scaleLength(metersPerPixel: number, unitMeters: number, maxPx: number): ScaleLength {
  const fitting = NICE_LENGTHS.filter((value) => (value * unitMeters) / metersPerPixel <= maxPx);
  const value = fitting.at(-1) ?? NICE_LENGTHS[0];
  const leading = Math.round(value / 10 ** Math.floor(Math.log10(value)));
  return { value, px: (value * unitMeters) / metersPerPixel, segments: leading === 5 ? 5 : 4 };
}

function formatLength(value: number): string {
  if (Number.isInteger(value)) return formatNumber(value);
  return formatNumber(value, Number.isInteger(value * 10) ? 1 : 2);
}

function Bar({ length, y }: { length: ScaleLength; y: number }) {
  const width = length.px / length.segments;
  return (
    <g>
      {Array.from({ length: length.segments }, (_, index) => (
        <rect
          key={index}
          x={0.5 + index * width}
          y={y + 0.5}
          width={width}
          height={BAR_HEIGHT_PX}
          style={{
            fill: index % 2 === 0 ? "var(--frame-ink)" : "var(--frame-paper)",
            stroke: "var(--frame-ink)",
            strokeWidth: 1,
          }}
        />
      ))}
    </g>
  );
}

function endLabelStart(length: ScaleLength): number {
  return length.px - (formatLength(length.value).length * CHAR_WIDTH_PX) / 2;
}

function endLabelText(length: ScaleLength, unit: string): string {
  return `${formatLength(length.value)} ${unit}`;
}

function EndLabel({ length, unit, y }: { length: ScaleLength; unit: string; y: number }) {
  return (
    <text x={endLabelStart(length)} y={y}>
      {endLabelText(length, unit)}
    </text>
  );
}

function ScaleGraphic({
  metersPerPixel,
  withNauticalMiles,
}: {
  metersPerPixel: number;
  withNauticalMiles: boolean;
}) {
  const km = scaleLength(metersPerPixel, METERS_PER_KM, KM_MAX_PX);
  const nm = scaleLength(metersPerPixel, METERS_PER_NM, NM_MAX_PX);
  const middle = km.segments === 4 ? formatLength(km.value / 2) : null;
  const height = withNauticalMiles ? 34 : 18;
  const width = withNauticalMiles
    ? SVG_WIDTH_PX
    : Math.ceil(endLabelStart(km) + endLabelText(km, "км").length * CHAR_WIDTH_PX + 2);
  return (
    <svg
      width={width}
      height={height}
      className="block fill-current font-mono text-[11px] font-medium"
      aria-hidden
    >
      <text x={0} y={9}>
        0
      </text>
      {middle ? (
        <text x={km.px / 2} y={9} textAnchor="middle">
          {middle}
        </text>
      ) : null}
      <EndLabel length={km} unit="км" y={9} />
      <Bar length={km} y={11} />
      {withNauticalMiles ? (
        <>
          <Bar length={nm} y={17} />
          <text x={0} y={32}>
            0
          </text>
          <EndLabel length={nm} unit="мор. миль" y={32} />
        </>
      ) : null}
    </svg>
  );
}

function scaleSummary(metersPerPixel: number, withNauticalMiles: boolean): string {
  const km = scaleLength(metersPerPixel, METERS_PER_KM, KM_MAX_PX);
  const nm = scaleLength(metersPerPixel, METERS_PER_NM, NM_MAX_PX);
  const kmText = `Масштабная линейка: ${formatLength(km.value)} км`;
  return withNauticalMiles ? `${kmText}, ${formatLength(nm.value)} мор. миль` : kmText;
}

function OverzoomNote() {
  const basemapId = useMapLayersStore((state) => state.basemapId);
  const zoom = useMapViewStore((state) => state.zoom);
  const note = findBasemap(basemapId).overzoomNote;
  if (!note || zoom < note.fromZoom) return null;
  return (
    <p className="border border-line-hairline bg-surface-panel px-2 py-0.5 text-[11px] text-text-secondary">
      {note.text}
    </p>
  );
}

type ScaleBarProps = { phone: boolean; style: CSSProperties };

export function ScaleBar({ phone, style }: ScaleBarProps) {
  const metersPerPixel = useMapViewStore((state) => state.metersPerPixel);
  if (!metersPerPixel) return null;
  const withNauticalMiles = !phone;
  return (
    <div
      className={cn("absolute flex flex-col gap-1", phone ? "items-start" : "items-end")}
      style={style}
    >
      <OverzoomNote />
      <div
        role="img"
        aria-label={scaleSummary(metersPerPixel, withNauticalMiles)}
        className="border border-line-hairline bg-surface-panel px-2 py-[3px] text-text-secondary"
      >
        <ScaleGraphic metersPerPixel={metersPerPixel} withNauticalMiles={withNauticalMiles} />
      </div>
    </div>
  );
}
