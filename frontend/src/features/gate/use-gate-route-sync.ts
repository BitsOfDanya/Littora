"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { isGateIdle, useGateStore } from "./gate-store";

export function useGateRouteSync(): void {
  const pathname = usePathname();

  useEffect(() => {
    if (pathname === "/") return;
    const { phase, setPhase, markWorkspaceShown } = useGateStore.getState();
    if (isGateIdle(phase)) setPhase("hidden");
    if (phase === "hidden" || isGateIdle(phase)) markWorkspaceShown();
  }, [pathname]);
}
