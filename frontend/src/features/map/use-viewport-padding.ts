"use client";

import type { Map as MapLibreMap, PaddingOptions } from "maplibre-gl";
import { type RefObject, useEffect, useRef } from "react";
import { create } from "zustand";
import type { LngLat } from "@/domain/geo";
import { overlayInsets, useOverlayRectsStore } from "./overlay-rects";
import { useMainMap } from "./use-main-map";

export type Padding = { top: number; right: number; bottom: number; left: number };

export const PADDING_EASE_MS = 240;

type ViewportPaddingStore = {
  target: Padding | null;
  setTarget: (target: Padding | null) => void;
};

export const useViewportPaddingStore = create<ViewportPaddingStore>()((set) => ({
  target: null,
  setTarget: (target) =>
    set((state) =>
      target && state.target && samePadding(state.target, target) ? state : { target },
    ),
}));

export function toPadding(padding: PaddingOptions): Padding {
  return {
    top: padding.top ?? 0,
    right: padding.right ?? 0,
    bottom: padding.bottom ?? 0,
    left: padding.left ?? 0,
  };
}

export function samePadding(a: Padding, b: Padding): boolean {
  return (
    Math.round(a.top) === Math.round(b.top) &&
    Math.round(a.right) === Math.round(b.right) &&
    Math.round(a.bottom) === Math.round(b.bottom) &&
    Math.round(a.left) === Math.round(b.left)
  );
}

export function standardEasing(t: number): number {
  const [x1, y1, x2, y2] = [0.2, 0, 0.38, 0.9];
  let low = 0;
  let high = 1;
  let u = t;
  for (let step = 0; step < 16; step += 1) {
    u = (low + high) / 2;
    const x = 3 * (1 - u) ** 2 * u * x1 + 3 * (1 - u) * u ** 2 * x2 + u ** 3;
    if (x < t) low = u;
    else high = u;
  }
  return 3 * (1 - u) ** 2 * u * y1 + 3 * (1 - u) * u ** 2 * y2 + u ** 3;
}

function readPixels(element: HTMLElement, property: string): number {
  const value = Number.parseFloat(getComputedStyle(element).getPropertyValue(property));
  return Number.isFinite(value) ? value : 0;
}

type LayoutBox = { top: number; right: number; bottom: number; left: number };

function layoutBox(element: HTMLElement): LayoutBox {
  let left = 0;
  let top = 0;
  for (let node: Element | null = element; node instanceof HTMLElement; node = node.offsetParent) {
    left += node.offsetLeft;
    top += node.offsetTop;
  }
  return { top, left, right: left + element.offsetWidth, bottom: top + element.offsetHeight };
}

function measurePadding(map: MapLibreMap, element: HTMLElement, minimum: Padding): Padding {
  const canvas = layoutBox(map.getContainer());
  const viewport = layoutBox(element);
  const frame = readPixels(element, "--frame");
  const overlays = overlayInsets(useOverlayRectsStore.getState().rects);
  const inner = (edge: keyof Padding) => Math.max(frame, overlays[edge], minimum[edge]);
  return {
    top: Math.round(Math.max(0, viewport.top - canvas.top) + inner("top")),
    right: Math.round(Math.max(0, canvas.right - viewport.right) + inner("right")),
    bottom: Math.round(Math.max(0, canvas.bottom - viewport.bottom) + inner("bottom")),
    left: Math.round(Math.max(0, viewport.left - canvas.left) + inner("left")),
  };
}

const VISIBILITY_MARGIN_PX = 72;

type PaddingApplier = { reconcile: () => void; dispose: () => void };

type PaddingSources = { measure: () => Padding; focus: () => LngLat | null };

function paddedCenter(padding: Padding, width: number, height: number) {
  return {
    x: padding.left + (width - padding.left - padding.right) / 2,
    y: padding.top + (height - padding.top - padding.bottom) / 2,
  };
}

function clampAxis(value: number, min: number, max: number): number {
  return min > max ? (min + max) / 2 : Math.min(Math.max(value, min), max);
}

function isInside(
  point: { x: number; y: number },
  padding: Padding,
  width: number,
  height: number,
): boolean {
  return (
    point.x >= padding.left &&
    point.x <= width - padding.right &&
    point.y >= padding.top &&
    point.y <= height - padding.bottom
  );
}

function centerKeepingVisible(
  map: MapLibreMap,
  target: Padding,
  focus: LngLat | null,
): [number, number] | undefined {
  if (!focus) return undefined;
  const { clientWidth: width, clientHeight: height } = map.getContainer();
  const current = toPadding(map.getPadding());
  const point = map.project([focus[0], focus[1]]);
  if (!isInside(point, current, width, height)) return undefined;
  const from = paddedCenter(current, width, height);
  const to = paddedCenter(target, width, height);
  const landed = { x: point.x + to.x - from.x, y: point.y + to.y - from.y };
  const dx =
    clampAxis(
      landed.x,
      target.left + VISIBILITY_MARGIN_PX,
      width - target.right - VISIBILITY_MARGIN_PX,
    ) - landed.x;
  const dy =
    clampAxis(
      landed.y,
      target.top + VISIBILITY_MARGIN_PX,
      height - target.bottom - VISIBILITY_MARGIN_PX,
    ) - landed.y;
  if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return undefined;
  const center = map.unproject([from.x - dx, from.y - dy]);
  return [center.lng, center.lat];
}

function createPaddingApplier(
  map: MapLibreMap,
  { measure, focus }: PaddingSources,
): PaddingApplier {
  let appliedOnce = false;
  let easingTo: Padding | null = null;
  let frame = 0;

  const startEase = (target: Padding) => {
    map.easeTo({
      padding: target,
      center: centerKeepingVisible(map, target, focus()),
      duration: PADDING_EASE_MS,
      easing: standardEasing,
    });
    easingTo = target;
  };

  const reconcile = () => {
    const target = measure();
    useViewportPaddingStore.getState().setTarget(target);
    if (!appliedOnce) {
      appliedOnce = true;
      if (!map.isMoving()) map.setPadding(target);
      else startEase(target);
      return;
    }
    if (easingTo) {
      if (!samePadding(easingTo, target)) startEase(target);
      return;
    }
    if (samePadding(toPadding(map.getPadding()), target) || map.isMoving()) return;
    startEase(target);
  };

  const handleMoveEnd = () => {
    easingTo = null;
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(reconcile);
  };

  map.on("moveend", handleMoveEnd);
  return {
    reconcile: () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(reconcile);
    },
    dispose: () => {
      cancelAnimationFrame(frame);
      map.off("moveend", handleMoveEnd);
    },
  };
}

type ViewportPaddingOptions = { minimum?: Partial<Padding>; keepVisible?: LngLat | null };

export function useViewportPadding(
  viewportRef: RefObject<HTMLElement | null>,
  { minimum = {}, keepVisible = null }: ViewportPaddingOptions = {},
): void {
  const map = useMainMap();
  const { top = 0, right = 0, bottom = 0, left = 0 } = minimum;
  const minimumRef = useRef<Padding>({ top, right, bottom, left });
  const focusRef = useRef<LngLat | null>(keepVisible);
  const applierRef = useRef<PaddingApplier | null>(null);

  useEffect(() => {
    focusRef.current = keepVisible;
  }, [keepVisible]);

  useEffect(() => {
    minimumRef.current = { top, right, bottom, left };
    applierRef.current?.reconcile();
  }, [top, right, bottom, left]);

  useEffect(() => {
    const element = viewportRef.current;
    if (!map || !element) return;
    const applier = createPaddingApplier(map, {
      measure: () => measurePadding(map, element, minimumRef.current),
      focus: () => focusRef.current,
    });
    applierRef.current = applier;
    applier.reconcile();
    const observer = new ResizeObserver(applier.reconcile);
    observer.observe(element);
    observer.observe(map.getContainer());
    const unsubscribe = useOverlayRectsStore.subscribe(applier.reconcile);
    return () => {
      observer.disconnect();
      unsubscribe();
      applier.dispose();
      applierRef.current = null;
    };
  }, [map, viewportRef]);
}
