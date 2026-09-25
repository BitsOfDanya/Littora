"use client";

import { useCallback, useSyncExternalStore } from "react";

export const MEDIA = {
  tabletUp: "(min-width: 768px)",
  laptopUp: "(min-width: 1280px)",
  wideUp: "(min-width: 1600px)",
  autoCollapse: "(max-width: 1380px)",
} as const;

export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    [query],
  );
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(query).matches,
    () => false,
  );
}
