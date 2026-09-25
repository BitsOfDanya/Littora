"use client";

import { useCallback, useRef } from "react";
import { usePreferencesStore } from "@/state/preferences-store";
import { useMainMap } from "../use-main-map";
import { type FrameColors, paintFrame } from "./frame-painter";
import { tickSpecFor } from "./ticks";
import { useFrameWidth } from "./use-frame-width";
import { useMapRedraw } from "./use-map-redraw";
import { viewportProjector } from "./viewport-projector";

const FALLBACK_FONT = "ui-monospace, monospace";

function readThemeFrameColors(): FrameColors {
  const style = getComputedStyle(document.documentElement);
  return {
    ink: style.getPropertyValue("--frame-ink").trim(),
    paper: style.getPropertyValue("--frame-paper").trim(),
    label: style.getPropertyValue("--frame-label").trim(),
  };
}

function readTickFontFamily(): string {
  return (
    getComputedStyle(document.documentElement).getPropertyValue("--font-data").trim() ||
    FALLBACK_FONT
  );
}

function fitCanvas(
  canvas: HTMLCanvasElement,
  width: number,
  height: number,
): CanvasRenderingContext2D | null {
  const ratio = window.devicePixelRatio || 1;
  const pixelWidth = Math.round(width * ratio);
  const pixelHeight = Math.round(height * ratio);
  if (canvas.width !== pixelWidth) canvas.width = pixelWidth;
  if (canvas.height !== pixelHeight) canvas.height = pixelHeight;
  const context = canvas.getContext("2d");
  context?.setTransform(ratio, 0, 0, ratio, 0, 0);
  return context;
}

type ChartFrameProps = {
  band?: number;
  colors?: FrameColors;
};

export function ChartFrame({ band, colors }: ChartFrameProps) {
  const map = useMainMap();
  const rootRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const themeBand = useFrameWidth();
  const theme = usePreferencesStore((state) => state.theme);
  const width = band ?? themeBand;

  const draw = useCallback(() => {
    const root = rootRef.current;
    const canvas = canvasRef.current;
    if (!map || !root || !canvas) return;
    const projector = viewportProjector(map, root);
    const context = fitCanvas(canvas, projector.width, projector.height);
    if (!context) return;
    paintFrame(context, {
      projector,
      band: width,
      ticks: tickSpecFor(map.getZoom()),
      colors: colors ?? readThemeFrameColors(),
      fontFamily: readTickFontFamily(),
    });
  }, [map, width, colors]);

  useMapRedraw(map, rootRef, draw, theme);

  return (
    <div ref={rootRef} aria-hidden className="pointer-events-none absolute inset-0">
      <canvas ref={canvasRef} className="absolute inset-0 size-full" />
    </div>
  );
}
