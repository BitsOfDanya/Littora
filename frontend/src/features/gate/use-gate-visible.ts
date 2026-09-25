"use client";

import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";
import { useGateStore } from "./gate-store";

const subscribeNever = () => () => {};

function useIsHydrating(): boolean {
  return useSyncExternalStore(
    subscribeNever,
    () => false,
    () => true,
  );
}

export function useGateVisible(): boolean {
  const phase = useGateStore((state) => state.phase);
  const pathname = usePathname();
  const hydrating = useIsHydrating();
  return phase !== "hidden" || (hydrating && pathname === "/");
}
