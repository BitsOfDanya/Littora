"use client";

import { useSyncExternalStore } from "react";

const subscribeNever = () => () => undefined;

export function useHydrated(): boolean {
  return useSyncExternalStore(
    subscribeNever,
    () => true,
    () => false,
  );
}
