"use client";

import type { Map as MapLibreMap } from "maplibre-gl";
import { type RefObject, useEffect, useRef } from "react";

export function useMapRedraw(
  map: MapLibreMap | undefined,
  elementRef: RefObject<HTMLElement | null>,
  draw: () => void,
  revision: unknown = null,
): void {
  const drawRef = useRef(draw);
  const scheduleRef = useRef<() => void>(() => undefined);

  useEffect(() => {
    drawRef.current = draw;
    scheduleRef.current();
  }, [draw, revision]);

  useEffect(() => {
    if (!map) return;
    let frame = 0;
    let active = true;
    const schedule = () => {
      if (frame || !active) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        drawRef.current();
      });
    };
    scheduleRef.current = schedule;
    schedule();
    map.on("move", schedule);
    map.on("resize", schedule);
    map.on("load", schedule);
    const observer = new ResizeObserver(schedule);
    if (elementRef.current) observer.observe(elementRef.current);
    void document.fonts?.ready.then(schedule);
    return () => {
      active = false;
      cancelAnimationFrame(frame);
      scheduleRef.current = () => undefined;
      map.off("move", schedule);
      map.off("resize", schedule);
      map.off("load", schedule);
      observer.disconnect();
    };
  }, [map, elementRef]);
}
