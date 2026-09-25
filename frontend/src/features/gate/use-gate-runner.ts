"use client";

import { type AnimationPlaybackControls, animate } from "motion/react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef } from "react";
import { findAoi } from "@/config/aois";
import { WORKSPACE_MODES, findModeByPathname } from "@/config/modes";
import { useWorkspaceStore } from "@/state/workspace-store";
import { GATE_RUN_MS, type GateRun, isOpeningRun } from "./gate-choreography";
import { gateClock } from "./gate-clock";
import { GATE_COPY } from "./gate-copy";
import { rememberOpened } from "./gate-session";
import { useGateStore } from "./gate-store";

export type GateRunner = {
  hold: () => void;
  seek: (ms: number) => void;
};

const SETTLE_TIMEOUT_MS = 2500;
const QUIET_FRAME_MS = 34;
const QUIET_FRAMES = 6;

function afterWorkspaceSettles(start: () => void): () => void {
  const startedAt = performance.now();
  let previous = startedAt;
  let quiet = 0;
  let frame = requestAnimationFrame(function step(now) {
    const navigated = window.location.pathname !== "/";
    quiet = navigated && now - previous < QUIET_FRAME_MS ? quiet + 1 : 0;
    previous = now;
    if (quiet >= QUIET_FRAMES || now - startedAt > SETTLE_TIMEOUT_MS) {
      start();
      return;
    }
    frame = requestAnimationFrame(step);
  });
  return () => cancelAnimationFrame(frame);
}

function focusActiveModeTab(): void {
  const tabs = document.querySelectorAll<HTMLElement>('a[aria-current="page"]');
  for (const tab of tabs) {
    if (tab.offsetParent === null) continue;
    tab.focus({ preventScroll: true });
    return;
  }
}

function openingAnnouncement(): string {
  const mode = findModeByPathname(window.location.pathname) ?? WORKSPACE_MODES[0];
  const aoi = findAoi(useWorkspaceStore.getState().aoiId);
  return GATE_COPY.announcement(mode.label, aoi?.name ?? "");
}

export function useGateRunner(): GateRunner {
  const router = useRouter();
  const run = useGateStore((state) => state.run);
  const controlsRef = useRef<AnimationPlaybackControls | null>(null);
  const manualRef = useRef(false);

  const complete = useCallback(
    (finished: GateRun) => {
      manualRef.current = false;
      controlsRef.current = null;
      if (isOpeningRun(finished)) {
        rememberOpened();
        useGateStore.getState().finishOpening(openingAnnouncement());
        requestAnimationFrame(focusActiveModeTab);
        return;
      }
      useGateStore.getState().finishClosing();
      if (window.location.pathname !== "/") router.push("/");
    },
    [router],
  );

  useEffect(() => {
    if (!run || manualRef.current) return;
    let controls: AnimationPlaybackControls | null = null;
    const start = () => {
      const total = GATE_RUN_MS[run];
      controls = animate(gateClock, total, {
        duration: Math.max(0, total - gateClock.get()) / 1000,
        ease: "linear",
        onComplete: () => complete(run),
      });
      controlsRef.current = controls;
    };
    if (!isOpeningRun(run)) {
      start();
      return () => controls?.stop();
    }
    const cancelWait = afterWorkspaceSettles(start);
    return () => {
      cancelWait();
      controls?.stop();
    };
  }, [run, complete]);

  return useMemo(
    () => ({
      hold: () => {
        manualRef.current = true;
        controlsRef.current?.stop();
      },
      seek: (ms: number) => {
        const current = useGateStore.getState().run;
        if (!current) return;
        const total = GATE_RUN_MS[current];
        gateClock.set(Math.min(Math.max(ms, 0), total));
        if (ms >= total) complete(current);
      },
    }),
    [complete],
  );
}
