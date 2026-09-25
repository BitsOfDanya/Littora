import type { CSSProperties } from "react";

export const GATE_LIVERY = {
  land: "#D8CB98",
  foreshore: "rgba(139,122,58,.14)",
  foreshoreLine: "#8B7A3A",
  engraving: "rgba(17,20,22,.18)",
  ink: "#111416",
  inkSecondary: "#4A4431",
  shallow: "#A9CFE3",
  middle: "#BFDCE8",
  deep: "#D6E9EF",
  isobath: "#7FA6B8",
  seam: "#FFFFFF",
  stamp: "#FFFFFF",
  staffWater: "rgba(169,207,227,.55)",
  framePaper: "#F5F4EF",
  frameInk: "rgba(17,20,22,.70)",
  frameChequerPaper: "#FFFFFF",
  frameLabel: "#5C6569",
} as const;

export const GATE_LIVERY_VARS = {
  "--gate-land": GATE_LIVERY.land,
  "--gate-ink": GATE_LIVERY.ink,
  "--gate-ink-secondary": GATE_LIVERY.inkSecondary,
  "--gate-seam": GATE_LIVERY.seam,
  "--gate-stamp": GATE_LIVERY.stamp,
  "--gate-frame-paper": GATE_LIVERY.framePaper,
} as CSSProperties;
