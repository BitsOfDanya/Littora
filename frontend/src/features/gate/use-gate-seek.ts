"use client";

import { useEffect } from "react";
import type { GateRun } from "./gate-choreography";
import { isGateIdle, useGateStore } from "./gate-store";
import type { GateRunner } from "./use-gate-runner";

declare global {
  interface Window {
    __gateSeek?: (ms: number, run?: GateRun) => void;
  }
}

export function useGateSeek(runner: GateRunner, startOpening: (run?: GateRun) => void): void {
  useEffect(() => {
    if (process.env.NODE_ENV !== "development") return;
    window.__gateSeek = (ms, run) => {
      runner.hold();
      const { phase, run: current, beginClosing } = useGateStore.getState();
      if (!current && isGateIdle(phase)) startOpening(run ?? "full");
      if (!current && phase === "hidden") beginClosing();
      runner.seek(ms);
    };
    return () => {
      delete window.__gateSeek;
    };
  }, [runner, startOpening]);
}
