"use client";

import { type MotionValue, useTransform } from "motion/react";
import { type GateFrame, gateFrame } from "./gate-choreography";
import { gateClock } from "./gate-clock";
import { useGateStore } from "./gate-store";
import { useGateVisible } from "./use-gate-visible";
import { usePrefersReducedMotion } from "./use-reduced-motion";

export function useGateValue<T>(select: (frame: GateFrame) => T): MotionValue<T> {
  const run = useGateStore((state) => state.run);
  const visible = useGateVisible();
  const reducedMotion = usePrefersReducedMotion();
  return useTransform(gateClock, (t) => select(gateFrame({ run, t, visible, reducedMotion })));
}
