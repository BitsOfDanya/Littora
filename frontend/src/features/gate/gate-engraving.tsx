"use client";

import type { Map as MapLibreMap } from "maplibre-gl";
import { motion } from "motion/react";
import { useEffect, useRef } from "react";
import { useMainMap } from "@/features/map/use-main-map";
import { IDLE_MAP_SCALE, scaleTransform } from "./gate-choreography";
import {
  drawGraticule,
  drawNeatline,
  type EngravingGeometry,
  type LeafSide,
} from "./draw-engraving";
import { useGateValue } from "./use-gate-value";
import { usePrefersReducedMotion } from "./use-reduced-motion";

type Layers = { graticule: HTMLCanvasElement; neatline: HTMLCanvasElement };

function readPx(styles: CSSStyleDeclaration, name: string): number {
  return Number.parseFloat(styles.getPropertyValue(name)) || 0;
}

function prepare(
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

function measure(
  leaf: HTMLElement,
  root: HTMLElement,
  side: LeafSide,
  fontSource: HTMLElement,
): EngravingGeometry {
  const rootStyles = getComputedStyle(root);
  return {
    side,
    width: leaf.clientWidth,
    height: leaf.clientHeight,
    top: leaf.offsetTop,
    rootHeight: root.clientHeight,
    frame: readPx(rootStyles, "--gate-frame"),
    gaugeColumn: readPx(rootStyles, "--gauge-col"),
    fontFamily: getComputedStyle(fontSource).fontFamily,
  };
}

function paint(
  layers: Layers,
  leaf: HTMLElement,
  root: HTMLElement,
  side: LeafSide,
  map: MapLibreMap,
  mapScale: number,
): void {
  const geometry = measure(leaf, root, side, layers.neatline);
  if (geometry.width === 0 || geometry.height === 0) return;
  layers.graticule.style.transformOrigin = `50% ${geometry.rootHeight / 2 - geometry.top}px`;
  const graticule = prepare(layers.graticule, geometry.width, geometry.height);
  const neatline = prepare(layers.neatline, geometry.width, geometry.height);
  if (graticule) drawGraticule(graticule, map, geometry);
  if (neatline) drawNeatline(neatline, map, geometry, mapScale);
}

export function GateEngraving({ side }: { side: LeafSide }) {
  const graticuleRef = useRef<HTMLCanvasElement>(null);
  const neatlineRef = useRef<HTMLCanvasElement>(null);
  const map = useMainMap();
  const idleScale = usePrefersReducedMotion() ? 1 : IDLE_MAP_SCALE;
  const transform = useGateValue((frame) => scaleTransform(frame.mapScale));

  useEffect(() => {
    const graticule = graticuleRef.current;
    const neatline = neatlineRef.current;
    const leaf = neatline?.closest<HTMLElement>("[data-gate-leaf]");
    const root = neatline?.closest<HTMLElement>("[data-gate-root]");
    if (!graticule || !neatline || !leaf || !root || !map) return;
    let frame = 0;
    let active = true;
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() =>
        paint({ graticule, neatline }, leaf, root, side, map, idleScale),
      );
    };
    schedule();
    const observer = new ResizeObserver(schedule);
    observer.observe(leaf);
    observer.observe(root);
    map.on("move", schedule);
    map.on("resize", schedule);
    void document.fonts?.ready.then(() => {
      if (active) schedule();
    });
    return () => {
      active = false;
      cancelAnimationFrame(frame);
      observer.disconnect();
      map.off("move", schedule);
      map.off("resize", schedule);
    };
  }, [map, side, idleScale]);

  return (
    <>
      <motion.canvas
        ref={graticuleRef}
        aria-hidden
        className="pointer-events-none absolute inset-0 size-full"
        style={{ transform }}
      />
      <canvas
        ref={neatlineRef}
        aria-hidden
        className="pointer-events-none absolute inset-0 size-full font-mono"
      />
    </>
  );
}
