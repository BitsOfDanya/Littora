"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";
import { scaleTransform } from "./gate-choreography";
import { useGateStore } from "./gate-store";
import { useGateValue } from "./use-gate-value";
import { useGateVisible } from "./use-gate-visible";

export function GateMapSettle({ children }: { children: ReactNode }) {
  const visible = useGateVisible();
  const transform = useGateValue((frame) => scaleTransform(frame.mapScale));
  const scrimOpacity = useGateValue((frame) => frame.scrimOpacity);
  return (
    <>
      <motion.div className="absolute inset-0" style={{ transform }} inert={visible}>
        {children}
      </motion.div>
      {visible ? (
        <motion.div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-surface-app"
          style={{ opacity: scrimOpacity }}
        />
      ) : null}
    </>
  );
}

export function GateInert({ children }: { children: ReactNode }) {
  const visible = useGateVisible();
  return (
    <div className="contents" inert={visible}>
      {children}
    </div>
  );
}

export function GateAnnouncer() {
  const announcement = useGateStore((state) => state.announcement);
  return (
    <p aria-live="polite" className="sr-only">
      {announcement}
    </p>
  );
}
