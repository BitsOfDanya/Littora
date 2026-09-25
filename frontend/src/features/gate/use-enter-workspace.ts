"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect } from "react";
import { DEFAULT_MODE_HREF } from "@/config/modes";
import type { GateRun } from "./gate-choreography";
import { chooseOpeningRun } from "./gate-session";
import { useGateStore } from "./gate-store";

export type EnterWorkspace = (run?: GateRun) => void;

export function useEnterWorkspace(): EnterWorkspace {
  const router = useRouter();

  useEffect(() => {
    router.prefetch(DEFAULT_MODE_HREF);
  }, [router]);

  return useCallback(
    (run) => {
      if (!useGateStore.getState().beginOpening(run ?? chooseOpeningRun())) return;
      if (window.location.pathname === "/") router.push(DEFAULT_MODE_HREF);
    },
    [router],
  );
}
