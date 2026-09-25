"use client";

import { useLayoutEffect } from "react";
import { useGateStore } from "./gate-store";
import { usePrefitWorkingCamera } from "./use-prefit-working-camera";

export function GateEntry() {
  usePrefitWorkingCamera();
  useLayoutEffect(() => {
    useGateStore.getState().arriveAtGate();
  }, []);
  return null;
}
