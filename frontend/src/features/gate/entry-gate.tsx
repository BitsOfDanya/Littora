"use client";

import { motion } from "motion/react";
import { type Ref, useEffect, useRef } from "react";
import { useHotkey } from "@/features/shell/hotkeys";
import { DepthBands, Foreshore } from "./gate-chart-ground";
import { GATE_COPY } from "./gate-copy";
import { GateLeaf } from "./gate-leaf";
import { GATE_LIVERY_VARS } from "./gate-livery";
import { isGateIdle, useGateStore } from "./gate-store";
import { LowerLeafContent } from "./lower-leaf";
import { LevelPointer } from "./staff-gauge";
import { UpperLeafContent } from "./upper-leaf";
import { useEnterWorkspace } from "./use-enter-workspace";
import { useGateRouteSync } from "./use-gate-route-sync";
import { useGateRunner } from "./use-gate-runner";
import { useGateSeek } from "./use-gate-seek";
import { useGateValue } from "./use-gate-value";
import { useGateVisible } from "./use-gate-visible";

const GATE_GEOMETRY =
  "[--seam:46%] md:[--seam:50%] [--gate-frame:0px] md:[--gate-frame:14px] xl:[--gate-frame:16px] 2xl:[--gate-frame:18px] [--gauge-col:12px] md:[--gauge-col:64px] [--gauge-ppm:110px] md:[--gauge-ppm:150px] md:[--gate-pad:clamp(24px,6.6vw,96px)]";

type GateOverlayProps = {
  opening: boolean;
  onOpen: () => void;
  buttonRef: Ref<HTMLButtonElement>;
};

function LandGround() {
  return (
    <>
      <div aria-hidden className="absolute inset-0 bg-(--gate-land)" />
      <Foreshore />
    </>
  );
}

function GateOverlay({ opening, onOpen, buttonRef }: GateOverlayProps) {
  const opacity = useGateValue((frame) => frame.gateOpacity);
  return (
    <div
      data-gate-root
      data-theme="day"
      role="region"
      aria-label={GATE_COPY.region}
      onClick={onOpen}
      className={`absolute inset-0 z-40 overflow-hidden text-(--gate-ink) [color-scheme:light] ${GATE_GEOMETRY}`}
      style={GATE_LIVERY_VARS}
    >
      <motion.div className="absolute inset-0" style={{ opacity }}>
        <GateLeaf side="upper" ground={<LandGround />}>
          <UpperLeafContent />
        </GateLeaf>
        <GateLeaf side="lower" ground={<DepthBands />}>
          <LowerLeafContent opening={opening} onOpen={onOpen} buttonRef={buttonRef} />
        </GateLeaf>
        <LevelPointer />
      </motion.div>
    </div>
  );
}

export function EntryGate() {
  const visible = useGateVisible();
  const phase = useGateStore((state) => state.phase);
  const idle = visible && (isGateIdle(phase) || phase === "hidden");
  const open = useEnterWorkspace();
  const runner = useGateRunner();
  const buttonRef = useRef<HTMLButtonElement>(null);

  useGateRouteSync();
  useGateSeek(runner, open);
  useHotkey(["Enter", "NumpadEnter"], () => open(), { enabled: idle });

  useEffect(() => {
    if (idle) buttonRef.current?.focus({ preventScroll: true });
  }, [idle]);

  if (!visible) return null;
  return <GateOverlay opening={phase === "opening"} onOpen={() => open()} buttonRef={buttonRef} />;
}
