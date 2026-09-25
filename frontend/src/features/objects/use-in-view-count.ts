"use client";

import { useCallback, useSyncExternalStore } from "react";
import type { LngLat } from "@/domain/geo";
import { useMainMap } from "@/features/map/use-main-map";
import { isInVisibleField } from "./visible-field";

const MAP_EVENTS = ["moveend", "resize", "load"] as const;

export function useInViewCount(points: readonly LngLat[]): number | null {
  const map = useMainMap();

  const subscribe = useCallback(
    (onChange: () => void) => {
      if (!map) return () => undefined;
      for (const event of MAP_EVENTS) map.on(event, onChange);
      return () => {
        for (const event of MAP_EVENTS) map.off(event, onChange);
      };
    },
    [map],
  );

  const snapshot = () =>
    map ? points.filter((point) => isInVisibleField(map, point)).length : null;

  return useSyncExternalStore(subscribe, snapshot, () => null);
}
