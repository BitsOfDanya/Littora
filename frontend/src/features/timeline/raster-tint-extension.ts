import { type Layer, LayerExtension } from "@deck.gl/core";
import type { RASTER_TINTS } from "@/config/basemaps";

export type RasterTint = (typeof RASTER_TINTS)["eox"]["night"];

type TintFactors = {
  brightnessLow: number;
  brightnessHigh: number;
  saturation: number;
  contrast: number;
};

function saturationFactor(saturation: number): number {
  return saturation > 0 ? 1 - 1 / (1.001 - saturation) : -saturation;
}

function contrastFactor(contrast: number): number {
  return contrast > 0 ? 1 / (1 - contrast) : 1 + contrast;
}

export function tintFactors(tint: RasterTint): TintFactors {
  return {
    brightnessLow: tint["raster-brightness-min"] ?? 0,
    brightnessHigh: tint["raster-brightness-max"] ?? 1,
    saturation: saturationFactor(tint["raster-saturation"] ?? 0),
    contrast: contrastFactor(tint["raster-contrast"] ?? 0),
  };
}

function glslFloat(value: number): string {
  const fixed = value.toFixed(5);
  return fixed.includes(".") ? fixed : `${fixed}.0`;
}

function tintShader({ brightnessLow, brightnessHigh, saturation, contrast }: TintFactors): string {
  return `
  float tintAverage = (color.r + color.g + color.b) / 3.0;
  color.rgb += (tintAverage - color.rgb) * ${glslFloat(saturation)};
  color.rgb = (color.rgb - 0.5) * ${glslFloat(contrast)} + 0.5;
  color.rgb = mix(vec3(${glslFloat(brightnessLow)}), vec3(${glslFloat(brightnessHigh)}), clamp(color.rgb, 0.0, 1.0));
`;
}

export class RasterTintExtension extends LayerExtension<TintFactors> {
  static extensionName = "RasterTintExtension";

  getShaders(this: Layer, extension: RasterTintExtension) {
    return { inject: { "fs:DECKGL_FILTER_COLOR": tintShader(extension.opts) } };
  }
}
