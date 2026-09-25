"use client";

import { type PointerEvent, useRef, useState } from "react";
import type { SheetDetent } from "@/state/shell-ui-store";
import { clampSheetHeight, type DetentHeights, detentForRelease } from "./sheet-detents";

const DRAG_SLOP_PX = 5;

type DragState = {
  pointerId: number;
  startY: number;
  startHeight: number;
  lastY: number;
  lastTime: number;
  velocity: number;
  moved: boolean;
};

type SheetDragHandlers = {
  onPointerDown: (event: PointerEvent<HTMLElement>) => void;
  onPointerMove: (event: PointerEvent<HTMLElement>) => void;
  onPointerUp: (event: PointerEvent<HTMLElement>) => void;
  onPointerCancel: (event: PointerEvent<HTMLElement>) => void;
};

export type SheetDrag = {
  liveHeight: number | null;
  handlers: SheetDragHandlers;
  consumeClick: () => boolean;
};

export function useSheetDrag(
  currentHeight: number,
  heights: DetentHeights,
  onSettle: (detent: SheetDetent) => void,
): SheetDrag {
  const [liveHeight, setLiveHeight] = useState<number | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const suppressClickRef = useRef(false);

  const finish = (event: PointerEvent<HTMLElement>, cancelled: boolean) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    dragRef.current = null;
    if (!drag.moved) return;
    suppressClickRef.current = true;
    const height = clampSheetHeight(drag.startHeight - (event.clientY - drag.startY), heights);
    setLiveHeight(null);
    if (!cancelled) onSettle(detentForRelease(height, drag.velocity, heights));
  };

  const handlers: SheetDragHandlers = {
    onPointerDown: (event) => {
      if (event.button !== 0) return;
      dragRef.current = {
        pointerId: event.pointerId,
        startY: event.clientY,
        startHeight: currentHeight,
        lastY: event.clientY,
        lastTime: event.timeStamp,
        velocity: 0,
        moved: false,
      };
    },
    onPointerMove: (event) => {
      const drag = dragRef.current;
      if (!drag || drag.pointerId !== event.pointerId) return;
      const offset = event.clientY - drag.startY;
      if (!drag.moved && Math.abs(offset) < DRAG_SLOP_PX) return;
      if (!drag.moved) event.currentTarget.setPointerCapture(event.pointerId);
      drag.moved = true;
      const elapsed = Math.max(1, event.timeStamp - drag.lastTime);
      drag.velocity = (event.clientY - drag.lastY) / elapsed;
      drag.lastY = event.clientY;
      drag.lastTime = event.timeStamp;
      setLiveHeight(clampSheetHeight(drag.startHeight - offset, heights));
    },
    onPointerUp: (event) => finish(event, false),
    onPointerCancel: (event) => finish(event, true),
  };

  const consumeClick = () => {
    const suppressed = suppressClickRef.current;
    suppressClickRef.current = false;
    return suppressed;
  };

  return { liveHeight, handlers, consumeClick };
}
