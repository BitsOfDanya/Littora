"use client";

import { useEffect, useRef } from "react";
import type { BBox, LngLat } from "@/domain/geo";
import { fitTo, isDefaultFitDone, isInVisibleField, targetPadding } from "./camera";
import { useMainMap } from "./use-main-map";

const LAYOUT_SETTLE_MS = 300;
const RETRY_MS = 200;
const MAX_WAIT_MS = 4_000;
const FIT_MS = 600;

export type FrameOnceOptions = {
  maxZoom: number;
  crampedShare: number;
  tighten: boolean;
  resetOnNull?: boolean;
};

export function useFrameOnce(
  key: string | null,
  bbox: BBox | null,
  { maxZoom, crampedShare, tighten, resetOnNull = false }: FrameOnceOptions,
): void {
  const map = useMainMap();
  const framedRef = useRef<string | null>(null);
  const frameRef = useRef({ bbox, maxZoom, crampedShare, tighten });

  useEffect(() => {
    frameRef.current = { bbox, maxZoom, crampedShare, tighten };
  }, [bbox, maxZoom, crampedShare, tighten]);

  useEffect(() => {
    if (!key) {
      if (resetOnNull) framedRef.current = null;
      return;
    }
    if (!map || framedRef.current === key) return;
    let userMoved = false;
    let timer = 0;
    let waited = 0;
    const onMoveStart = (event: { originalEvent?: unknown }) => {
      if (event.originalEvent) userMoved = true;
    };
    const frame = () => {
      if (userMoved) return;
      if ((!isDefaultFitDone() || map.isMoving()) && waited < MAX_WAIT_MS) {
        waited += RETRY_MS;
        timer = window.setTimeout(frame, RETRY_MS);
        return;
      }
      map.off("movestart", onMoveStart);
      const current = frameRef.current;
      if (!current.bbox) return;
      framedRef.current = key;
      const [west, south, east, north] = current.bbox;
      const padding = targetPadding(map);
      const corners: LngLat[] = [
        [west, south],
        [west, north],
        [east, south],
        [east, north],
      ];
      const [low, high] = [map.project([west, south]), map.project([east, north])];
      const container = map.getContainer();
      const share = Math.max(
        Math.abs(high.x - low.x) / (container.clientWidth - padding.left - padding.right),
        Math.abs(high.y - low.y) / (container.clientHeight - padding.top - padding.bottom),
      );
      const cramped =
        current.tighten && map.getZoom() < current.maxZoom && share < current.crampedShare;
      if (!cramped && corners.every((corner) => isInVisibleField(map, corner, padding))) return;
      fitTo(map, current.bbox, { durationMs: FIT_MS, maxZoom: current.maxZoom, padding });
    };
    map.on("movestart", onMoveStart);
    timer = window.setTimeout(frame, LAYOUT_SETTLE_MS);
    return () => {
      window.clearTimeout(timer);
      map.off("movestart", onMoveStart);
    };
  }, [map, key, resetOnNull]);
}
