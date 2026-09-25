"use client";

import { overlayInsets, useOverlayRectsStore } from "../overlay-rects";
import { useCartoucheWidth, useFrameWidth, useIsPhoneWidth } from "./use-frame-width";

export const FURNITURE_GAP_PX = 12;
const TOOL_SIZE_PX = { desktop: 32, phone: 40 } as const;
const STAMP_HEIGHT_PX = 24;
const CARTOUCHE_STRIP_HEIGHT_PX = 40;
const LABEL_CLEARANCE_PX = 8;
const SCALE_BAR_HEIGHT_PX = 40;

export type Edges = { top: number; right: number; bottom: number; left: number };

export type FurnitureLayout = {
  phone: boolean;
  frame: number;
  stamp: { top: number; left: number; right: number };
  scale: { bottom: number; left?: number; right?: number };
  labelInterior: Edges;
};

export function useFurnitureLayout(): FurnitureLayout {
  const phone = useIsPhoneWidth();
  const frame = useFrameWidth();
  const cartouche = useCartoucheWidth();
  const rects = useOverlayRectsStore((state) => state.rects);
  const insets = overlayInsets(rects);

  const inner = frame + FURNITURE_GAP_PX;
  const tools = phone ? TOOL_SIZE_PX.phone : TOOL_SIZE_PX.desktop;
  const cartoucheEdge = cartouche ? inner + cartouche : 0;
  const leftOccupied = Math.max(insets.left, cartoucheEdge);
  const bottomOccupied = Math.max(frame, insets.bottom);

  return {
    phone,
    frame,
    stamp: {
      top: inner,
      left: Math.max(inner, leftOccupied + FURNITURE_GAP_PX),
      right: inner + tools + FURNITURE_GAP_PX,
    },
    scale: phone
      ? { bottom: bottomOccupied + FURNITURE_GAP_PX, left: inner }
      : { bottom: bottomOccupied + FURNITURE_GAP_PX, right: inner },
    labelInterior: {
      top: inner + Math.max(STAMP_HEIGHT_PX, CARTOUCHE_STRIP_HEIGHT_PX) + LABEL_CLEARANCE_PX,
      right: inner + tools + LABEL_CLEARANCE_PX,
      bottom: bottomOccupied + FURNITURE_GAP_PX + SCALE_BAR_HEIGHT_PX + LABEL_CLEARANCE_PX,
      left: Math.max(frame, insets.left) + LABEL_CLEARANCE_PX,
    },
  };
}
