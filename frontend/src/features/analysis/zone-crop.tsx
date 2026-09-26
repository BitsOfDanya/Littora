"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { GROUND_INK } from "@/features/map/palette";
import { type Analysis, type AnalysisLayer, analysisFileUrl } from "@/lib/api/analyses";
import { formatNumber } from "@/lib/format/numbers";
import { Checkbox } from "@/ui/checkbox";
import {
  cropPixel,
  type CropView,
  cropView,
  type ImageFrame,
  imageFrame,
  type RealZone,
  ringsOf,
  toFrameMeters,
} from "./zones";

const CROP_HEIGHT = 196;
const MIN_EXTENT_M = 400;
const SCALE_STEPS_M = [50, 100, 200, 500, 1000, 2000, 5000];
const INK = GROUND_INK.dark;
const RASTER = "absolute bg-[length:100%_100%] bg-no-repeat [image-rendering:pixelated]";

function useWidth() {
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

function useNaturalWidth(url: string | null): number | null {
  const [loaded, setLoaded] = useState<{ url: string; width: number } | null>(null);
  useEffect(() => {
    if (!url) return;
    const probe = new Image();
    probe.onload = () => setLoaded({ url, width: probe.naturalWidth });
    probe.src = url;
    return () => {
      probe.onload = null;
    };
  }, [url]);
  return loaded && loaded.url === url && loaded.width > 0 ? loaded.width : null;
}

function placement(view: CropView, base: ImageFrame, layer: AnalysisLayer) {
  const [topLeft, , bottomRight] = layer.corners;
  const [left, top] = toFrameMeters(base, [topLeft[0], topLeft[1]]);
  const [right, bottom] = toFrameMeters(base, [bottomRight[0], bottomRight[1]]);
  return {
    left: (left - view.x) * view.scale,
    top: (top - view.y) * view.scale,
    width: (right - left) * view.scale,
    height: (bottom - top) * view.scale,
  };
}

function scaleBar(view: CropView): number {
  const target = view.widthM / 4;
  return SCALE_STEPS_M.reduce((best, step) => (step <= target ? step : best), SCALE_STEPS_M[0]);
}

export function ZoneCrop({ analysis, zone }: { analysis: Analysis; zone: RealZone }) {
  const { ref, width } = useWidth();
  const [showProbability, setShowProbability] = useState(true);
  const { image, probability } = analysis.layers;
  const imageUrl = analysisFileUrl(analysis.id, "image.png");
  const imagePixels = useNaturalWidth(image ? imageUrl : null);
  const frame = useMemo(() => (image ? imageFrame(image) : null), [image]);
  const rings = useMemo(() => ringsOf(zone.geometry), [zone.geometry]);
  const points = useMemo(
    () => (rings.length ? rings.flat() : zone.centroid ? [zone.centroid] : []),
    [rings, zone.centroid],
  );
  const view = frame ? cropView(frame, points, width, CROP_HEIGHT, MIN_EXTENT_M) : null;

  if (!image || !frame)
    return (
      <p className="text-[12px] leading-4 text-text-secondary">
        Снимка у анализа нет — вырезку показать нечем.
      </p>
    );

  const paths = view
    ? rings.map(
        (ring) =>
          ring
            .map((point, index) => {
              const [x, y] = cropPixel(view, frame, point);
              return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
            })
            .join(" ") + " Z",
      )
    : [];
  const center = view && zone.centroid ? cropPixel(view, frame, zone.centroid) : null;
  const barM = view ? scaleBar(view) : 0;
  const imageBox = view ? placement(view, frame, image) : null;
  const probabilityBox = view && probability ? placement(view, frame, probability) : null;

  return (
    <div className="flex flex-col gap-1.5">
      <div
        ref={ref}
        className="relative overflow-hidden rounded-[var(--radius-ctl)] border border-line-hairline bg-surface-sunken"
        style={{ height: CROP_HEIGHT }}
      >
        {imageBox ? (
          <div
            role="img"
            aria-label={`Снимок Sentinel-2 вокруг ${zone.id}`}
            className={RASTER}
            style={{ ...imageBox, backgroundImage: `url(${imageUrl})` }}
          />
        ) : null}
        {probabilityBox && showProbability ? (
          <div
            aria-hidden
            className={RASTER}
            style={{
              ...probabilityBox,
              backgroundImage: `url(${analysisFileUrl(analysis.id, "probability.png")})`,
            }}
          />
        ) : null}
        {view ? (
          <svg
            width={width}
            height={CROP_HEIGHT}
            className="absolute inset-0"
            aria-hidden
            viewBox={`0 0 ${width} ${CROP_HEIGHT}`}
          >
            {paths.map((d) => (
              <g key={d}>
                <path d={d} fill="none" stroke={INK.halo} strokeWidth={3.5} />
                <path d={d} fill="none" stroke={INK.selection} strokeWidth={1.5} />
              </g>
            ))}
            {!paths.length && center ? (
              <circle cx={center[0]} cy={center[1]} r={8} fill="none" stroke={INK.selection} />
            ) : null}
            <rect
              x={6}
              y={CROP_HEIGHT - 26}
              width={barM * view.scale + 44}
              height={20}
              fill={INK.halo}
            />
            <rect
              x={10}
              y={CROP_HEIGHT - 12}
              width={barM * view.scale}
              height={3}
              fill={INK.label}
            />
            <text
              x={barM * view.scale + 16}
              y={CROP_HEIGHT - 9}
              fill={INK.label}
              className="font-mono text-[11px]"
            >
              {barM >= 1000 ? `${formatNumber(barM / 1000)} км` : `${barM} м`}
            </text>
          </svg>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] leading-[14px] text-text-tertiary">
        <span>
          RGB анализа
          {imagePixels ? `, пиксель ≈ ${formatNumber(frame.widthM / imagePixels)} м` : ""} · контур
          — пиксели выше порога
        </span>
        {probability ? (
          <Checkbox checked={showProbability} onChange={setShowProbability}>
            вероятность
          </Checkbox>
        ) : null}
      </div>
    </div>
  );
}
