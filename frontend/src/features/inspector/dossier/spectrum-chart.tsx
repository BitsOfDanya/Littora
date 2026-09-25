"use client";

import { useId, useMemo, useState } from "react";
import type { BandReflectance } from "@/domain/detection";
import { SENTINEL2_BANDS, type Sentinel2BandId } from "@/domain/sentinel2";
import { formatNumber } from "@/lib/format/numbers";
import { cn } from "@/ui/cn";
import {
  AXIS_SEGMENTS,
  BAND_WIDTH_NM,
  type BrokenAxis,
  breakX,
  niceMax,
  wavelengthToX,
} from "./wavelength-axis";

export type SpectrumTone = "spot" | "plastic" | "sargassum" | "foam" | "water" | "pinned";

export type SpectrumSeries = {
  key: string;
  label: string;
  tone: SpectrumTone;
  bands: readonly BandReflectance[];
  sigma?: readonly BandReflectance[];
};

const WIDTH = 360;
const PLOT = { top: 10, bottom: 128, left: 34, right: 8 };
const RIBBON_BASE = 150;
const RIBBON_HEIGHT = { 10: 18, 20: 12, 60: 7.5 } as const;
const HEIGHT = 168;
const AXIS: BrokenAxis = { left: PLOT.left, width: WIDTH - PLOT.left - PLOT.right, gap: 8 };
const FDI_BANDS: ReadonlySet<Sentinel2BandId> = new Set(["B06", "B08", "B11"]);
const NM_TICKS = [500, 600, 700, 800, 900, 1600, 2200] as const;

const TONE_STROKE: Record<SpectrumTone, string> = {
  spot: "stroke-accent-selection",
  plastic: "stroke-[#4A9BD6] day:stroke-[#1F63B5]",
  sargassum: "stroke-[#2FA878] day:stroke-[#0F8062]",
  foam: "stroke-[#B5891C] day:stroke-[#9C7A00]",
  water: "stroke-text-tertiary",
  pinned: "stroke-text-secondary",
};

const TONE_DASH: Record<SpectrumTone, string> = {
  spot: "5 3",
  plastic: "4 2.5",
  sargassum: "4 2.5",
  foam: "4 2.5",
  water: "1.5 2.5",
  pinned: "1 2",
};

const BAND_BY_ID = new Map(SENTINEL2_BANDS.map((band) => [band.id, band]));

function nmOf(band: Sentinel2BandId): number {
  return BAND_BY_ID.get(band)?.centralWavelengthNm ?? 0;
}

function segmentsOf(bands: readonly BandReflectance[]): BandReflectance[][] {
  const sorted = [...bands].sort((a, b) => nmOf(a.band) - nmOf(b.band));
  const near = sorted.filter((entry) => nmOf(entry.band) <= AXIS_SEGMENTS[0].to);
  const far = sorted.filter((entry) => nmOf(entry.band) >= AXIS_SEGMENTS[1].from);
  return [near, far].filter((segment) => segment.length > 0);
}

function valueOf(bands: readonly BandReflectance[] | undefined, band: Sentinel2BandId) {
  return bands?.find((entry) => entry.band === band)?.reflectance;
}

export function SpectrumLegendSample({ tone }: { tone: SpectrumTone }) {
  return (
    <svg width="18" height="8" aria-hidden className="shrink-0">
      {tone === "spot" ? (
        <rect x="0" y="1" width="18" height="6" className="fill-accent-selection/15" />
      ) : null}
      <line
        x1="0"
        x2="18"
        y1="4"
        y2="4"
        strokeWidth={tone === "spot" ? 1.8 : 1.4}
        strokeDasharray={TONE_DASH[tone]}
        className={TONE_STROKE[tone]}
      />
    </svg>
  );
}

export function SpectrumChart({
  series,
  title,
  illustration,
}: {
  series: readonly SpectrumSeries[];
  title: string;
  illustration: boolean;
}) {
  const patternId = useId();
  const [hovered, setHovered] = useState<Sentinel2BandId | null>(null);
  const bandIds = useMemo(
    () =>
      [...new Set(series.flatMap((entry) => entry.bands.map((band) => band.band)))].sort(
        (a, b) => nmOf(a) - nmOf(b),
      ),
    [series],
  );
  const maxValue = niceMax(
    Math.max(
      0.05,
      ...series.flatMap((entry) =>
        entry.bands.map((band) => band.reflectance + (valueOf(entry.sigma, band.band) ?? 0)),
      ),
    ),
  );
  const x = (nm: number) => wavelengthToX(nm, AXIS);
  const y = (value: number) =>
    PLOT.bottom - (Math.max(value, 0) / maxValue) * (PLOT.bottom - PLOT.top);
  const spot = series.find((entry) => entry.tone === "spot");
  const hoveredBand = hovered ? BAND_BY_ID.get(hovered) : undefined;
  const gap = breakX(AXIS);

  return (
    <figure className="relative flex flex-col gap-1">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={title}
        className="w-full"
        onMouseLeave={() => setHovered(null)}
      >
        <defs>
          <pattern
            id={patternId}
            width="6"
            height="6"
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(45)"
          >
            <line x1="0" y1="0" x2="0" y2="6" className="stroke-line-hairline" strokeWidth="1.2" />
          </pattern>
        </defs>
        <rect
          x={PLOT.left}
          y={PLOT.top}
          width={AXIS.width}
          height={PLOT.bottom - PLOT.top}
          fill={illustration ? `url(#${patternId})` : "none"}
        />
        {SENTINEL2_BANDS.filter((band) => band.id !== "B10" && band.id !== "B09").map((band) => {
          const half = BAND_WIDTH_NM[band.id] / 2;
          const left = x(band.centralWavelengthNm - half);
          const width = Math.max(2, x(band.centralWavelengthNm + half) - left);
          const fdi = FDI_BANDS.has(band.id);
          return (
            <rect
              key={band.id}
              x={left}
              y={PLOT.top}
              width={width}
              height={PLOT.bottom - PLOT.top}
              className={cn(
                fdi ? "fill-text-tertiary/25" : "fill-text-tertiary/8",
                hovered === band.id && "fill-text-tertiary/35",
              )}
            />
          );
        })}
        {[0, maxValue / 2, maxValue].map((value) => (
          <g key={value}>
            <line
              x1={PLOT.left}
              x2={WIDTH - PLOT.right}
              y1={y(value)}
              y2={y(value)}
              className="stroke-line-hairline"
            />
            <text
              x={PLOT.left - 4}
              y={y(value) + 3.5}
              textAnchor="end"
              className="fill-text-tertiary font-mono text-[10.5px]"
            >
              {formatNumber(value, 2)}
            </text>
          </g>
        ))}
        <rect
          x={gap - AXIS.gap / 2}
          y={PLOT.top - 2}
          width={AXIS.gap}
          height={RIBBON_BASE - PLOT.top + 4}
          className="fill-surface-panel"
        />
        <path
          d={`M${gap - 5} ${PLOT.bottom + 3} l4 -6 M${gap + 1} ${PLOT.bottom + 3} l4 -6`}
          className="stroke-text-tertiary"
          strokeWidth="1"
        />
        {spot?.sigma
          ? segmentsOf(spot.bands).map((segment) => {
              const upper = segment.map(
                (entry) =>
                  `${x(nmOf(entry.band))},${y(entry.reflectance + (valueOf(spot.sigma, entry.band) ?? 0))}`,
              );
              const lower = [...segment]
                .reverse()
                .map(
                  (entry) =>
                    `${x(nmOf(entry.band))},${y(entry.reflectance - (valueOf(spot.sigma, entry.band) ?? 0))}`,
                );
              return (
                <polygon
                  key={`sigma-${segment[0].band}`}
                  points={[...upper, ...lower].join(" ")}
                  className="fill-accent-selection/15"
                />
              );
            })
          : null}
        {[...series]
          .sort((a, b) => (a.tone === "spot" ? 1 : b.tone === "spot" ? -1 : 0))
          .flatMap((entry) =>
            segmentsOf(entry.bands).map((segment) => (
              <polyline
                key={`${entry.key}-${segment[0].band}`}
                fill="none"
                strokeWidth={entry.tone === "spot" ? 1.8 : 1.3}
                strokeDasharray={
                  illustration || entry.tone !== "spot" ? TONE_DASH[entry.tone] : undefined
                }
                strokeLinejoin="round"
                className={TONE_STROKE[entry.tone]}
                points={segment
                  .map((band) => `${x(nmOf(band.band))},${y(band.reflectance)}`)
                  .join(" ")}
              />
            )),
          )}
        {spot
          ? spot.bands.map((band) => (
              <circle
                key={band.band}
                cx={x(nmOf(band.band))}
                cy={y(band.reflectance)}
                r={illustration ? 1.8 : 3}
                className={
                  illustration
                    ? "fill-surface-panel stroke-accent-selection"
                    : "fill-accent-selection"
                }
                strokeWidth={1.2}
              />
            ))
          : null}
        {SENTINEL2_BANDS.map((band) => {
          const height = RIBBON_HEIGHT[band.resolutionM as 10 | 20 | 60];
          const cx = x(band.centralWavelengthNm);
          const cirrus = band.id === "B10";
          return (
            <rect
              key={`ribbon-${band.id}`}
              x={cx - 3}
              y={RIBBON_BASE - height}
              width={6}
              height={height}
              strokeDasharray={cirrus ? "1 1" : undefined}
              className={cn(
                cirrus
                  ? "fill-none stroke-text-tertiary"
                  : FDI_BANDS.has(band.id)
                    ? "fill-[#E4E9EB] day:fill-[#111416]"
                    : "fill-text-tertiary/50",
              )}
            >
              <title>{`${band.id} · ${band.centralWavelengthNm} нм · ${band.resolutionM} м · ${band.name}`}</title>
            </rect>
          );
        })}
        {NM_TICKS.map((nm) => (
          <text
            key={nm}
            x={x(nm)}
            y={HEIGHT - 3}
            textAnchor="middle"
            className="fill-text-tertiary font-mono text-[10.5px]"
          >
            {nm}
          </text>
        ))}
        <text
          x={PLOT.left - 4}
          y={HEIGHT - 3}
          textAnchor="end"
          className="fill-text-tertiary font-mono text-[10.5px]"
        >
          нм
        </text>
        {bandIds.map((band) => {
          const nm = nmOf(band);
          const half = Math.max(BAND_WIDTH_NM[band] / 2, 12);
          const left = x(nm - half);
          return (
            <rect
              key={`hit-${band}`}
              x={left}
              y={PLOT.top}
              width={Math.max(8, x(nm + half) - left)}
              height={RIBBON_BASE - PLOT.top}
              fill="transparent"
              onMouseEnter={() => setHovered(band)}
            />
          );
        })}
      </svg>
      {hoveredBand ? (
        <div
          role="tooltip"
          className="pointer-events-none absolute top-1 z-10 flex flex-col gap-0.5 rounded-[var(--radius-ctl)] bg-primary-fill px-2 py-1 text-[11px] leading-[14px] text-primary-text"
          style={
            x(hoveredBand.centralWavelengthNm) > WIDTH / 2
              ? { right: `${(1 - x(hoveredBand.centralWavelengthNm) / WIDTH) * 100 + 3}%` }
              : { left: `${(x(hoveredBand.centralWavelengthNm) / WIDTH) * 100 + 3}%` }
          }
        >
          <span className="font-mono">
            {hoveredBand.id} · {hoveredBand.centralWavelengthNm} нм · {hoveredBand.resolutionM} м
            {FDI_BANDS.has(hoveredBand.id) ? " · FDI" : ""}
          </span>
          {series.map((entry) => {
            const value = valueOf(entry.bands, hoveredBand.id);
            if (value === undefined) return null;
            const sigma = valueOf(entry.sigma, hoveredBand.id);
            return (
              <span key={entry.key} className="flex justify-between gap-3">
                <span>{entry.label}</span>
                <span className="font-mono">
                  {formatNumber(value, 3)}
                  {sigma !== undefined ? ` ± ${formatNumber(sigma, 3)}` : ""}
                </span>
              </span>
            );
          })}
        </div>
      ) : null}
    </figure>
  );
}
