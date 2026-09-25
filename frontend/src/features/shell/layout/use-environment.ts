"use client";

import { useSyncExternalStore } from "react";

export type ShellLayout = "phone" | "tablet" | "laptop-compact" | "laptop" | "desktop";

const QUERIES: readonly [ShellLayout, string][] = [
  ["desktop", "(min-width: 1440px)"],
  ["laptop", "(min-width: 1280px)"],
  ["laptop-compact", "(min-width: 1024px)"],
  ["tablet", "(min-width: 768px)"],
];

const noSubscription = () => () => undefined;

function currentLayout(): ShellLayout {
  return QUERIES.find(([, query]) => window.matchMedia(query).matches)?.[0] ?? "phone";
}

function subscribe(onChange: () => void): () => void {
  const lists = QUERIES.map(([, query]) => window.matchMedia(query));
  lists.forEach((list) => list.addEventListener("change", onChange));
  return () => lists.forEach((list) => list.removeEventListener("change", onChange));
}

export function useShellLayout(): ShellLayout {
  return useSyncExternalStore(subscribe, currentLayout, () => "desktop");
}

export function useIsPhone(): boolean {
  return useShellLayout() === "phone";
}

export function allowsInlineQueue(layout: ShellLayout): boolean {
  return layout === "laptop" || layout === "desktop";
}

export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const list = window.matchMedia("(prefers-reduced-motion: reduce)");
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => false,
  );
}

export function useIsMacPlatform(): boolean {
  return useSyncExternalStore(
    noSubscription,
    () => /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent),
    () => false,
  );
}

export function useHydrated(): boolean {
  return useSyncExternalStore(
    noSubscription,
    () => true,
    () => false,
  );
}
