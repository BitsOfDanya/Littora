import { cssColorToRgba, hexToRgba, type Rgba, withAlpha } from "./color";
import { BEACHING, type ByGround, DRIFT, type Ground, SURVEY } from "./ramps";

export type GroundInk = {
  outline: string;
  halo: string;
  label: string;
  water: string;
  selection: string;
  hover: string;
  graticule: string;
  aoi: string;
  nodata: string;
};

export const GROUND_INK: ByGround<GroundInk> = {
  dark: {
    outline: "#E4F1F3",
    halo: "rgba(5,8,10,.78)",
    label: "#EEF6F7",
    water: "#B4D3E1",
    selection: "#E29BF5",
    hover: "#FFFFFF",
    graticule: "rgba(228,241,243,.14)",
    aoi: "#E29BF5",
    nodata: "#8A969A",
  },
  light: {
    outline: "#0B0F10",
    halo: "rgba(247,249,249,.86)",
    label: "#111416",
    water: "#2A5A78",
    selection: "#9C3399",
    hover: "#000000",
    graticule: "rgba(17,20,22,.16)",
    aoi: "#9C3399",
    nodata: "#6E7C80",
  },
};

export type MapPalette = {
  ground: Ground;
  selection: Rgba;
  outline: Rgba;
  halo: Rgba;
  hover: Rgba;
  aoi: Rgba;
  current: Rgba;
  forecastPath: Rgba;
  forecastEnvelope: Rgba;
  target: Rgba;
  targetFill: Rgba;
  caution: Rgba;
  alarm: Rgba;
};

function buildPalette(ground: Ground): MapPalette {
  const ink = GROUND_INK[ground];
  const drift = DRIFT.ink[ground];
  const survey = SURVEY.ink[ground];
  const beaching = BEACHING.ink[ground];
  return {
    ground,
    selection: hexToRgba(ink.selection),
    outline: hexToRgba(ink.outline, 230),
    halo: cssColorToRgba(ink.halo),
    hover: hexToRgba(ink.hover),
    aoi: hexToRgba(ink.aoi),
    current: withAlpha(hexToRgba(drift.particle), DRIFT.particleAlphaMax),
    forecastPath: hexToRgba(drift.median, 240),
    forecastEnvelope: hexToRgba(drift.envelope),
    target: hexToRgba(survey.mark),
    targetFill: hexToRgba(survey.ringFill, 240),
    caution: hexToRgba(beaching.caution),
    alarm: hexToRgba(beaching.alarm),
  };
}

const PALETTES: ByGround<MapPalette> = { dark: buildPalette("dark"), light: buildPalette("light") };

export function mapPaletteFor(ground: Ground): MapPalette {
  return PALETTES[ground];
}
