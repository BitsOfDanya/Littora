import { cubicBezier } from "motion/react";

export type GateRun = "full" | "repeat" | "fade" | "close" | "close-fade";

export const OPENING_RUNS: readonly GateRun[] = ["full", "repeat", "fade"];

export const GATE_RUN_MS: Record<GateRun, number> = {
  full: 1400,
  repeat: 520,
  fade: 160,
  close: 520,
  "close-fade": 160,
};

export const EQUALISED_AT_MS = 320;
export const CHAMBER_DEPTH_M = 0.3;
export const UNLATCH_PX = 5;
export const IDLE_MAP_SCALE = 1.02;
export const IDLE_SCRIM = 0.45;
const IDLE_SEAM = 0.5;

export type GateFrame = {
  travel: number;
  unlatchPx: number;
  gateOpacity: number;
  seamOpacity: number;
  shadowOpacity: number;
  scrimOpacity: number;
  mapScale: number;
  pointerOpacity: number;
  equalised: number;
  buttonShiftPx: number;
};

export type GateFrameInput = {
  run: GateRun | null;
  t: number;
  visible: boolean;
  reducedMotion: boolean;
};

const easeStd = cubicBezier(0.2, 0, 0.38, 0.9);
const easeHeavy = cubicBezier(0.72, 0, 0.18, 1);
const easeSettle = cubicBezier(0.2, 0, 0.2, 1);
const easeGauge = cubicBezier(0.33, 1, 0.68, 1);
const linear = (value: number) => value;

function span(
  t: number,
  start: number,
  end: number,
  ease: (value: number) => number = linear,
): number {
  if (t <= start) return 0;
  if (t >= end) return 1;
  return ease((t - start) / (end - start));
}

const HIDDEN_FRAME: GateFrame = {
  travel: 1,
  unlatchPx: 0,
  gateOpacity: 0,
  seamOpacity: 1,
  shadowOpacity: 0,
  scrimOpacity: 0,
  mapScale: 1,
  pointerOpacity: 0,
  equalised: 1,
  buttonShiftPx: 0,
};

function idleFrame(reducedMotion: boolean): GateFrame {
  return {
    travel: 0,
    unlatchPx: 0,
    gateOpacity: 1,
    seamOpacity: IDLE_SEAM,
    shadowOpacity: 0,
    scrimOpacity: IDLE_SCRIM,
    mapScale: reducedMotion ? 1 : IDLE_MAP_SCALE,
    pointerOpacity: 1,
    equalised: 0,
    buttonShiftPx: 0,
  };
}

function fullOpening(t: number): GateFrame {
  const settle = span(t, 380, 1300, easeSettle);
  return {
    travel: span(t, 400, 1280, easeHeavy),
    unlatchPx: UNLATCH_PX * span(t, 320, 400, easeStd),
    gateOpacity: 1,
    seamOpacity: IDLE_SEAM + (1 - IDLE_SEAM) * span(t, 320, 400),
    shadowOpacity: span(t, 400, 480) * (1 - span(t, 1080, 1280)),
    scrimOpacity: IDLE_SCRIM * (1 - settle),
    mapScale: 1 + (IDLE_MAP_SCALE - 1) * (1 - settle),
    pointerOpacity: 1 - span(t, 280, 400),
    equalised: span(t, 0, EQUALISED_AT_MS, easeGauge),
    buttonShiftPx: span(t, 0, 70, easeStd),
  };
}

function repeatOpening(t: number): GateFrame {
  const settle = span(t, 0, 440, easeSettle);
  return {
    travel: span(t, 0, 440, easeHeavy),
    unlatchPx: 0,
    gateOpacity: 1,
    seamOpacity: IDLE_SEAM + (1 - IDLE_SEAM) * span(t, 0, 80),
    shadowOpacity: span(t, 0, 60) * (1 - span(t, 340, 440)),
    scrimOpacity: IDLE_SCRIM * (1 - settle),
    mapScale: 1 + (IDLE_MAP_SCALE - 1) * (1 - settle),
    pointerOpacity: 0,
    equalised: 1,
    buttonShiftPx: span(t, 0, 70, easeStd),
  };
}

function fadeOpening(t: number): GateFrame {
  return { ...idleFrame(true), gateOpacity: 1 - span(t, 0, 160), scrimOpacity: 0, equalised: 1 };
}

function closing(t: number): GateFrame {
  const progress = span(t, 0, 520, easeStd);
  return {
    travel: 1 - progress,
    unlatchPx: 0,
    gateOpacity: 1,
    seamOpacity: IDLE_SEAM,
    shadowOpacity: 1 - span(t, 400, 520),
    scrimOpacity: IDLE_SCRIM * progress,
    mapScale: 1 + (IDLE_MAP_SCALE - 1) * progress,
    pointerOpacity: span(t, 440, 520),
    equalised: 0,
    buttonShiftPx: 0,
  };
}

function fadeClosing(t: number): GateFrame {
  return { ...idleFrame(true), gateOpacity: span(t, 0, 160) };
}

export function gateFrame({ run, t, visible, reducedMotion }: GateFrameInput): GateFrame {
  if (!visible) return HIDDEN_FRAME;
  switch (run) {
    case "full":
      return fullOpening(t);
    case "repeat":
      return repeatOpening(t);
    case "fade":
      return fadeOpening(t);
    case "close":
      return closing(t);
    case "close-fade":
      return fadeClosing(t);
    default:
      return idleFrame(reducedMotion);
  }
}

export function isOpeningRun(run: GateRun | null): boolean {
  return run !== null && OPENING_RUNS.includes(run);
}

export function leafTransform(side: "upper" | "lower", frame: GateFrame): string {
  if (frame.travel === 0 && frame.unlatchPx === 0) return "none";
  const sign = side === "upper" ? -1 : 1;
  const percent = sign * frame.travel * 100;
  const pixels = sign * (1 - frame.travel) * frame.unlatchPx;
  const operator = pixels < 0 ? "-" : "+";
  return `translateY(calc(${percent.toFixed(3)}% ${operator} ${Math.abs(pixels).toFixed(3)}px))`;
}

export function scaleTransform(scale: number): string {
  return scale === 1 ? "none" : `scale(${scale.toFixed(5)})`;
}
