"use client";

import { type RefObject, useEffect } from "react";
import { create } from "zustand";

export type OverlayEdge = "left" | "right" | "top" | "bottom";

type OverlayRect = { edge: OverlayEdge; size: number };

type OverlayRectsStore = {
  rects: Readonly<Record<string, OverlayRect>>;
  setRect: (id: string, rect: OverlayRect | null) => void;
};

export const useOverlayRectsStore = create<OverlayRectsStore>()((set) => ({
  rects: {},
  setRect: (id, rect) =>
    set((state) => {
      const current = state.rects[id];
      if (rect && current && current.edge === rect.edge && current.size === rect.size) return state;
      const rects = { ...state.rects };
      if (rect) rects[id] = rect;
      else delete rects[id];
      return { rects };
    }),
}));

export function overlayInsets(
  rects: Readonly<Record<string, OverlayRect>>,
): Record<OverlayEdge, number> {
  const insets: Record<OverlayEdge, number> = { left: 0, right: 0, top: 0, bottom: 0 };
  for (const rect of Object.values(rects))
    insets[rect.edge] = Math.max(insets[rect.edge], rect.size);
  return insets;
}

export function useRegisterOverlayRect(
  id: string,
  ref: RefObject<HTMLElement | null>,
  edge: OverlayEdge,
  enabled = true,
): void {
  const setRect = useOverlayRectsStore((state) => state.setRect);

  useEffect(() => {
    const element = ref.current;
    if (!element || !enabled) {
      setRect(id, null);
      return;
    }
    let frame = 0;
    const measure = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const box = element.getBoundingClientRect();
        const offsetParent = element.offsetParent as HTMLElement | null;
        const parent = offsetParent?.getBoundingClientRect();
        if (!parent) return;
        const size =
          edge === "left"
            ? box.right - parent.left
            : edge === "right"
              ? parent.right - box.left
              : edge === "top"
                ? box.bottom - parent.top
                : parent.bottom - box.top;
        setRect(id, { edge, size: Math.max(0, Math.round(size)) });
      });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      setRect(id, null);
    };
  }, [id, ref, edge, enabled, setRect]);
}
