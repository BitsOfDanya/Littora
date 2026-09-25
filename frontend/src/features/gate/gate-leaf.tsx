"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";
import { cn } from "@/ui/cn";
import type { LeafSide } from "./draw-engraving";
import { leafTransform } from "./gate-choreography";
import { GateEngraving } from "./gate-engraving";
import { StaffHalf } from "./staff-gauge";
import { useGateValue } from "./use-gate-value";

const FRAME_BORDER: Record<LeafSide, string> = {
  upper: "var(--gate-frame) var(--gate-frame) 0",
  lower: "0 var(--gate-frame) var(--gate-frame)",
};

function FramePaper({ side }: { side: LeafSide }) {
  return (
    <div
      aria-hidden
      className="absolute inset-y-0 right-(--gauge-col) left-0 border-solid border-(--gate-frame-paper)"
      style={{ borderWidth: FRAME_BORDER[side] }}
    />
  );
}

type GateLeafProps = {
  side: LeafSide;
  ground: ReactNode;
  children: ReactNode;
};

export function GateLeaf({ side, ground, children }: GateLeafProps) {
  const transform = useGateValue((frame) => leafTransform(side, frame));
  const shadowOpacity = useGateValue((frame) => frame.shadowOpacity);
  const seamOpacity = useGateValue((frame) => frame.seamOpacity);
  const upper = side === "upper";

  return (
    <motion.div
      data-gate-leaf={side}
      className={cn(
        "absolute inset-x-0",
        upper ? "top-0 h-[calc(var(--seam)-2px)]" : "top-[calc(var(--seam)+2px)] bottom-0",
      )}
      style={{ transform }}
    >
      <motion.div
        aria-hidden
        className="absolute inset-0 shadow-[0_0_24px_rgba(0,0,0,.35)]"
        style={{ opacity: shadowOpacity }}
      />
      <div className="absolute inset-0 overflow-hidden">
        {ground}
        <FramePaper side={side} />
        <GateEngraving side={side} />
        {children}
        <StaffHalf side={side} />
        <motion.span
          aria-hidden
          className={cn("absolute inset-x-0 h-px bg-(--gate-seam)", upper ? "bottom-0" : "top-0")}
          style={{ opacity: seamOpacity }}
        />
      </div>
    </motion.div>
  );
}
