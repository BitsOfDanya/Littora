"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { TILE_URLS } from "@/config/basemaps";
import type { CoverageCell } from "@/data/monitor-passes";
import type { ConfidenceClass } from "@/domain/detection";
import type { LngLat } from "@/domain/geo";
import { easeToIfOutside } from "@/features/map/camera";
import { colorForValue, isBelowRamp } from "@/features/map/color";
import { GROUND_INK } from "@/features/map/palette";
import { rampFor } from "@/features/map/ramps";
import { useMainMap } from "@/features/map/use-main-map";
import { usePreferencesStore } from "@/state/preferences-store";
import { Button } from "@/ui/button";
import { Checkbox } from "@/ui/checkbox";
import { Segmented } from "@/ui/segmented";
import {
  chipTiles,
  type ChipView,
  chipView,
  metersPerPixel,
  projectToChip,
  tileUrl,
} from "./evidence-view";

const CHIP_HEIGHT = 176;
const INK = GROUND_INK.dark;
const RAMP = rampFor("coverage", "dark");
const CANVAS_FILTER = {
  night: "saturate(0.72) contrast(1.15) brightness(0.92)",
  day: "saturate(0.88) contrast(1.06)",
} as const;
const OUTLINE_DASH: Record<ConfidenceClass, string | undefined> = {
  likely: undefined,
  possible: "4 2.5",
  low: "0.8 2",
};
const PLANNED_REASON = "Нужен снимок даты — каталог сцен не подключён (scene_catalog: planned)";

type ChipStatus = "loading" | "ready" | "error";
type ViewMode = "rgb" | "nir" | "fdi";

function useContainerWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return { ref, width };
}

function useTileCanvas(view: ChipView | null, filter: string, attempt: number) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [status, setStatus] = useState<ChipStatus>("loading");

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !view) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.round(view.width * ratio);
    canvas.height = Math.round(view.height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.imageSmoothingEnabled = true;
    const tiles = chipTiles(view);
    let settled = 0;
    let failed = 0;
    let cancelled = false;
    setStatus("loading");
    const images = tiles.map((tile) => {
      const image = new Image();
      image.crossOrigin = "anonymous";
      image.decoding = "async";
      image.onload = () => {
        if (cancelled) return;
        context.filter = filter;
        context.drawImage(image, tile.left, tile.top, tile.size, tile.size);
        settled += 1;
        if (settled === tiles.length) setStatus(failed ? "error" : "ready");
      };
      image.onerror = () => {
        if (cancelled) return;
        failed += 1;
        settled += 1;
        if (settled === tiles.length) setStatus("error");
      };
      image.src = tileUrl(TILE_URLS.eox2025, tile);
      return image;
    });
    return () => {
      cancelled = true;
      for (const image of images) {
        image.onload = null;
        image.onerror = null;
      }
    };
  }, [view, filter, attempt]);

  return { canvasRef, status };
}

function pathOf(view: ChipView, points: readonly LngLat[]): string {
  return (
    points
      .map((point, index) => {
        const [x, y] = projectToChip(view, point);
        return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(" ") + " Z"
  );
}

function Brackets({ view, ring }: { view: ChipView; ring: readonly LngLat[] }) {
  const projected = ring.map((point) => projectToChip(view, point));
  const left = Math.min(...projected.map(([x]) => x)) - 8;
  const right = Math.max(...projected.map(([x]) => x)) + 8;
  const top = Math.min(...projected.map(([, y]) => y)) - 8;
  const bottom = Math.max(...projected.map(([, y]) => y)) + 8;
  const arm = 8;
  const d = [
    `M${left} ${top + arm}V${top}H${left + arm}`,
    `M${right - arm} ${top}H${right}V${top + arm}`,
    `M${right} ${bottom - arm}V${bottom}H${right - arm}`,
    `M${left + arm} ${bottom}H${left}V${bottom - arm}`,
  ].join(" ");
  return (
    <>
      <path d={d} fill="none" stroke={INK.halo} strokeWidth={3.5} />
      <path d={d} fill="none" stroke={INK.selection} strokeWidth={1.5} />
    </>
  );
}

function ScaleAndNorth({ view, latitude }: { view: ChipView; latitude: number }) {
  const barPx = 1000 / metersPerPixel(latitude, view.zoom);
  const x0 = 10;
  const y0 = view.height - 14;
  return (
    <>
      <rect x={x0 - 4} y={y0 - 14} width={barPx + 36} height={24} fill={INK.halo} />
      <rect x={x0} y={y0} width={barPx / 2} height={4} fill={INK.label} />
      <rect
        x={x0 + barPx / 2}
        y={y0}
        width={barPx / 2}
        height={4}
        fill="none"
        stroke={INK.label}
        strokeWidth={1}
      />
      <text x={x0} y={y0 - 3} fill={INK.label} className="font-mono text-[10.5px]">
        0
      </text>
      <text x={x0 + barPx + 3} y={y0 + 5} fill={INK.label} className="font-mono text-[10.5px]">
        1 км
      </text>
      <g transform={`translate(${view.width - 18} 10)`}>
        <rect x={-8} y={-3} width={16} height={26} fill={INK.halo} />
        <path d="M0 0 L4.5 13 L0 10 L-4.5 13 Z" fill={INK.label} />
        <text x={0} y={21} textAnchor="middle" fill={INK.label} className="font-mono text-[10.5px]">
          N
        </text>
      </g>
    </>
  );
}

export function EvidenceChip({
  geometry,
  cells,
  confidence,
  focus,
}: {
  geometry: GeoJSON.Polygon;
  cells: readonly CoverageCell[];
  confidence: ConfidenceClass;
  focus: LngLat;
}) {
  const map = useMainMap();
  const theme = usePreferencesStore((state) => state.theme);
  const { ref, width } = useContainerWidth();
  const [mode, setMode] = useState<ViewMode>("rgb");
  const [mask, setMask] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const ring = useMemo(
    () => (geometry.coordinates[0] ?? []).map(([lng, lat]) => [lng, lat] as LngLat),
    [geometry],
  );
  const view = useMemo(
    () => (width > 0 && ring.length ? chipView(ring, width, CHIP_HEIGHT) : null),
    [ring, width],
  );
  const { canvasRef, status } = useTileCanvas(view, CANVAS_FILTER[theme], attempt);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Segmented<ViewMode>
          label="Вид снимка"
          value={mode}
          onChange={setMode}
          options={[
            { value: "rgb", label: "RGB", title: "Естественные цвета · B04 B03 B02" },
            { value: "nir", label: "NIR", disabled: true, disabledReason: PLANNED_REASON },
            { value: "fdi", label: "FDI", disabled: true, disabledReason: PLANNED_REASON },
          ]}
        />
        <Checkbox checked={mask} onChange={setMask} className="min-h-6 py-0">
          Маска
        </Checkbox>
        <Button
          size="sm"
          className="ml-auto"
          title="Показать пятно на карте"
          onClick={() => {
            if (map) easeToIfOutside(map, focus);
          }}
        >
          На карте
        </Button>
      </div>
      <div
        ref={ref}
        className="relative overflow-hidden border border-line-hairline bg-surface-sunken"
        style={{ height: CHIP_HEIGHT }}
      >
        <canvas
          ref={canvasRef}
          aria-hidden
          className="absolute inset-0"
          style={{ width: view?.width ?? 0, height: CHIP_HEIGHT }}
        />
        {view ? (
          <svg
            role="img"
            aria-label="Снимок пятна: мозаика EOX 2025 с контуром кандидата, масштаб 1 км, север вверху"
            className="absolute inset-0"
            width={view.width}
            height={CHIP_HEIGHT}
            viewBox={`0 0 ${view.width} ${CHIP_HEIGHT}`}
          >
            {mask ? (
              <>
                {cells.map((cell) =>
                  isBelowRamp(RAMP, cell.coverage) ? null : (
                    <path
                      key={cell.key}
                      d={pathOf(view, cell.polygon.slice(0, -1))}
                      fill={colorForValue(RAMP, cell.coverage)}
                      fillOpacity={0.88}
                    />
                  ),
                )}
                <path d={pathOf(view, ring)} fill="none" stroke={INK.halo} strokeWidth={3.5} />
                <path
                  d={pathOf(view, ring)}
                  fill="none"
                  stroke={INK.selection}
                  strokeWidth={1.8}
                  strokeDasharray={OUTLINE_DASH[confidence]}
                />
              </>
            ) : (
              <Brackets view={view} ring={ring} />
            )}
            <ScaleAndNorth view={view} latitude={focus[1]} />
          </svg>
        ) : null}
        {status === "loading" ? (
          <p className="absolute inset-x-0 top-2 text-center text-[12px] text-text-secondary">
            <span className="bg-surface-panel px-1.5 py-0.5">загрузка снимка…</span>
          </p>
        ) : null}
        {status === "error" ? (
          <p className="absolute inset-x-0 top-2 flex items-center justify-center gap-2 text-[12px] text-text-secondary">
            <span className="bg-surface-panel px-1.5 py-0.5">Снимок недоступен</span>
            <Button size="sm" onClick={() => setAttempt((value) => value + 1)}>
              Повторить
            </Button>
          </p>
        ) : null}
      </div>
      <p className="text-[11px] leading-[14px] text-text-tertiary">
        Мозаика EOX 2025 вместо снимка даты — сцена не подключена
      </p>
    </div>
  );
}
