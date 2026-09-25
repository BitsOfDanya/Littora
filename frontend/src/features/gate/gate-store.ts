import { create } from "zustand";
import type { GateRun } from "./gate-choreography";
import { gateClock } from "./gate-clock";

export type GatePhase = "hidden" | "closed" | "opening" | "closing";

type GateStore = {
  phase: GatePhase;
  run: GateRun | null;
  workspaceShown: boolean;
  announcement: string;
  setPhase: (phase: GatePhase) => void;
  arriveAtGate: () => void;
  beginOpening: (run: GateRun) => boolean;
  beginClosing: () => boolean;
  finishOpening: (announcement: string) => void;
  finishClosing: () => void;
  markWorkspaceShown: () => void;
};

export function isGateIdle(phase: GatePhase): boolean {
  return phase === "closed";
}

export function prefersReducedMotionNow(): boolean {
  return (
    typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

export const useGateStore = create<GateStore>()((set, get) => ({
  phase: "hidden",
  run: null,
  workspaceShown: false,
  announcement: "",
  setPhase: (phase) => set({ phase }),
  arriveAtGate: () => {
    const { phase, workspaceShown, beginClosing } = get();
    if (phase !== "hidden") return;
    if (workspaceShown) beginClosing();
    else set({ phase: "closed" });
  },
  beginOpening: (run) => {
    if (!isGateIdle(get().phase)) return false;
    gateClock.set(0);
    set({ phase: "opening", run, announcement: "" });
    return true;
  },
  beginClosing: () => {
    if (get().phase !== "hidden") return false;
    gateClock.set(0);
    set({ phase: "closing", run: prefersReducedMotionNow() ? "close-fade" : "close" });
    return true;
  },
  finishOpening: (announcement) =>
    set({ phase: "hidden", run: null, workspaceShown: true, announcement }),
  finishClosing: () => set({ phase: "closed", run: null }),
  markWorkspaceShown: () => {
    if (!get().workspaceShown) set({ workspaceShown: true });
  },
}));
