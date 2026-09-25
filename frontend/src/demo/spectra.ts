import type { BandReflectance, SpectralSignature } from "@/domain/detection";
import type { Estimate } from "@/domain/measurement";
import type { Sentinel2BandId } from "@/domain/sentinel2";
import { spectralIndices } from "@/domain/spectral-indices";

export const SPECTRUM_BANDS: readonly Sentinel2BandId[] = [
  "B01",
  "B02",
  "B03",
  "B04",
  "B05",
  "B06",
  "B07",
  "B08",
  "B8A",
  "B11",
  "B12",
];

export const OPEN_WATER = [
  0.085, 0.07, 0.05, 0.032, 0.028, 0.024, 0.023, 0.021, 0.02, 0.023, 0.019,
];

export const FLOATING_PLASTIC = [
  0.07, 0.074, 0.08, 0.078, 0.092, 0.095, 0.13, 0.16, 0.15, 0.075, 0.055,
];

const SENSOR_NOISE = 0.0018;

export function toBands(values: readonly number[]): BandReflectance[] {
  return SPECTRUM_BANDS.map((band, index) => ({
    band,
    reflectance: Math.round(values[index] * 10_000) / 10_000,
  }));
}

export function turbidWater(turbidity: number): number[] {
  return OPEN_WATER.map(
    (value, index) => value + (index < 5 ? turbidity * (5 - index) * 0.0015 : 0),
  );
}

export function mixedPixelSignature(coverage: number, turbidity = 0): SpectralSignature {
  const water = turbidWater(turbidity);
  const candidate = water.map(
    (value, index) => value * (1 - coverage) + FLOATING_PLASTIC[index] * coverage,
  );
  const candidateBands = toBands(candidate);
  return {
    candidate: candidateBands,
    surroundingWater: toBands(water),
    indices: spectralIndices(candidateBands),
  };
}

export function mixedPixelSpread(coverage: Estimate, turbidity = 0): BandReflectance[] {
  const water = turbidWater(turbidity);
  const halfRange = (coverage.high - coverage.low) / 3.29;
  return toBands(
    water.map((value, index) =>
      Math.hypot(Math.abs(FLOATING_PLASTIC[index] - value) * halfRange, SENSOR_NOISE),
    ),
  );
}
