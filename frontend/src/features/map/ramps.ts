import type { BasemapId } from "@/state/map-layers-store";
import type { ThemeId } from "@/state/preferences-store";
import type { StepRamp } from "./color";

export type Ground = "dark" | "light";

export type ByGround<T> = Readonly<Record<Ground, T>>;

export const groundOf = (basemap: BasemapId, theme: ThemeId): Ground =>
  basemap === "chart" && theme === "day" ? "light" : "dark";

export type RampId = "coverage" | "change" | "currentSpeed" | "surveyValue";

export const COVERAGE_STOPS = [0.01, 0.03, 0.06, 0.1, 0.15, 0.2] as const;
export const CHANGE_STOPS_PP = [-10, -6, -2, 2, 6] as const;
export const CURRENT_SPEED_STOPS_MS = [0, 0.1, 0.25, 0.5] as const;
export const SURVEY_VALUE_STOPS = [0, 0.2, 0.4, 0.6, 0.8] as const;

export const RAMPS: Readonly<Record<RampId, ByGround<StepRamp>>> = {
  coverage: {
    dark: {
      stops: COVERAGE_STOPS,
      colors: ["#1F2F4A", "#3B4A6B", "#6F7470", "#A69C5E", "#DCC24F", "#FDEB6E"],
    },
    light: {
      stops: COVERAGE_STOPS,
      colors: ["#F3E9A6", "#D9C25A", "#A89A4E", "#6F7465", "#3D4C73", "#13295B"],
    },
  },
  change: {
    dark: {
      stops: CHANGE_STOPS_PP,
      colors: ["#B7C9F2", "#4C79A8", "#1A1D21", "#8A7A3F", "#EDE09C"],
    },
    light: {
      stops: CHANGE_STOPS_PP,
      colors: ["#2A6BB0", "#8FB3DA", "#F1F1EC", "#C9B55A", "#8E7F0E"],
    },
  },
  currentSpeed: {
    dark: { stops: CURRENT_SPEED_STOPS_MS, colors: ["#1C2B33", "#2E6F7E", "#6FC3D4", "#D6F5FA"] },
    light: { stops: CURRENT_SPEED_STOPS_MS, colors: ["#E4F1F3", "#8CC7D2", "#2A8FA3", "#0B4F5E"] },
  },
  surveyValue: {
    dark: {
      stops: SURVEY_VALUE_STOPS,
      colors: ["#2A3238", "#4E5A62", "#7D8A92", "#B3BEC4", "#E6ECEF"],
    },
    light: {
      stops: SURVEY_VALUE_STOPS,
      colors: ["#E6ECEF", "#B3BEC4", "#7D8A92", "#4E5A62", "#2A3238"],
    },
  },
};

export function rampFor(layer: RampId, ground: Ground): StepRamp {
  return RAMPS[layer][ground];
}

export const COVERAGE_RAMP: StepRamp = RAMPS.coverage.dark;

export const HOTSPOT_ALPHA = 0.55;

export type ConfidenceLevel = "high" | "medium" | "low";

export type LineStyle = { dash: readonly [number, number]; widthPx: number };

export const CONFIDENCE_LINES: Readonly<Record<ConfidenceLevel, LineStyle>> = {
  high: { dash: [0, 0], widthPx: 1.6 },
  medium: { dash: [4, 2.5], widthPx: 1.4 },
  low: { dash: [0.6, 1.8], widthPx: 1.4 },
};

export const CONFIDENCE_INK: ByGround<{ outline: string; lowHatch: string }> = {
  dark: { outline: "#E4F1F3", lowHatch: "rgba(228,241,243,.35)" },
  light: { outline: "#0B0F10", lowHatch: "rgba(11,15,16,.35)" },
};

export const CONFIDENCE_LOW_HATCH_SPACING_PX = 8;

export const UNCERTAINTY = {
  threshold: 0.45,
  denseAbove: 0.6,
  spacingPx: { sparse: 8, dense: 5 },
  lineWidthPx: 1,
  ink: {
    dark: { hatch: "rgba(228,241,243,.55)", desaturateToward: "#9AA6A9" },
    light: { hatch: "rgba(11,15,16,.50)", desaturateToward: "#6E7C80" },
  } satisfies ByGround<{ hatch: string; desaturateToward: string }>,
} as const;

export const NO_DATA = {
  spacingPx: 8,
  lineWidthPx: 1,
  lineAlpha: 0.55,
  edgeDash: [4, 3] as const,
  edgeWidthPx: 1.2,
  ink: {
    dark: { line: "#8A969A", underlay: "rgba(10,14,17,.35)" },
    light: { line: "#6E7C80", underlay: "rgba(233,231,224,.35)" },
  } satisfies ByGround<{ line: string; underlay: string }>,
} as const;

export const DRIFT = {
  particleAlphaMax: 0.4,
  medianDash: [6, 4] as const,
  hindcastDash: [1, 3] as const,
  envelopeFillAlpha: { 6: 0.22, 12: 0.18, 24: 0.14, 48: 0.1, 72: 0.07 } as const,
  ink: {
    dark: { particle: "#9FD3E2", particleAlpha: 0.35, envelope: "#9FD3E2", median: "#E4F1F3" },
    light: { particle: "#2B6F86", particleAlpha: 0.4, envelope: "#2B6F86", median: "#0B0F10" },
  } satisfies ByGround<{
    particle: string;
    particleAlpha: number;
    envelope: string;
    median: string;
  }>,
} as const;

export const BEACHING = {
  widthPx: 5,
  haloPx: 8,
  ink: {
    dark: { alarm: "#FF6B7D", caution: "#F0913F", halo: "rgba(5,8,10,.8)" },
    light: { alarm: "#B0303F", caution: "#8A5A00", halo: "#FFFFFF" },
  } satisfies ByGround<{ alarm: string; caution: string; halo: string }>,
} as const;

export const SURVEY = {
  ringRadiusPx: 11,
  ringWidthPx: 2.2,
  searchRadiusDash: [2, 3] as const,
  searchRadiusWidthPx: 1.2,
  routeDash: [8, 4] as const,
  routeWidthPx: 2,
  routeHaloPx: 5,
  ink: {
    dark: { mark: "#E29BF5", ringFill: "#0A0E11" },
    light: { mark: "#9C3399", ringFill: "#FFFFFF" },
  } satisfies ByGround<{ mark: string; ringFill: string }>,
} as const;

export type ReferenceSpectrumId = "sargassum" | "plastic" | "foam";

export const REFERENCE_SPECTRA: ByGround<Readonly<Record<ReferenceSpectrumId, string>>> = {
  dark: { sargassum: "#2FA878", plastic: "#4A9BD6", foam: "#B5891C" },
  light: { sargassum: "#0F8062", plastic: "#1F63B5", foam: "#9C7A00" },
};

export type BandTintId = "red" | "green" | "blue" | "index";

export const BAND_TINTS: ByGround<Readonly<Record<BandTintId, string>>> = {
  dark: { red: "#E0776B", green: "#62B884", blue: "#6A9BE6", index: "#E4E9EB" },
  light: { red: "#B8473D", green: "#2F8A57", blue: "#2F66C2", index: "#111416" },
};
