"use client";

import { useSyncExternalStore } from "react";
import { useLayerVisible } from "@/state/map-layers-store";

export const PHONE_MAX_WIDTH = 767;

const FRAME_BY_MIN_WIDTH: readonly (readonly [minWidth: number, frame: number])[] = [
  [1440, 18],
  [1280, 16],
  [768, 14],
  [430, 8],
];

const CARTOUCHE_WIDE_MIN_WIDTH = 1440;

export function cartoucheWidthFor(viewportWidth: number): number {
  if (viewportWidth <= PHONE_MAX_WIDTH) return 0;
  return viewportWidth >= CARTOUCHE_WIDE_MIN_WIDTH ? 304 : 288;
}

export function frameWidthFor(viewportWidth: number): number {
  return FRAME_BY_MIN_WIDTH.find(([minWidth]) => viewportWidth >= minWidth)?.[1] ?? 0;
}

function subscribeToResize(callback: () => void): () => void {
  window.addEventListener("resize", callback);
  return () => window.removeEventListener("resize", callback);
}

function useWindowDerived<T>(derive: (width: number) => T, serverValue: T): T {
  return useSyncExternalStore(
    subscribeToResize,
    () => derive(window.innerWidth),
    () => serverValue,
  );
}

const isPhoneWidth = (width: number) => width <= PHONE_MAX_WIDTH;

export function useIsPhoneWidth(): boolean {
  return useWindowDerived(isPhoneWidth, false);
}

export function useCartoucheWidth(): number {
  return useWindowDerived(cartoucheWidthFor, 304);
}

export function useFrameBandWidth(): number {
  return useWindowDerived(frameWidthFor, 18);
}

export function useFrameWidth(): number {
  const band = useFrameBandWidth();
  const visible = useLayerVisible("graticule");
  return visible ? band : 0;
}
