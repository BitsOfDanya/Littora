import { describe, expect, it } from "vitest";
import type { BandReflectance } from "./detection";
import {
  floatingAlgaeIndex,
  floatingDebrisIndex,
  normalizedDifferenceVegetationIndex,
} from "./spectral-indices";

const bands = (values: Record<string, number>): BandReflectance[] =>
  Object.entries(values).map(([band, reflectance]) => ({ band, reflectance }) as BandReflectance);

const openWater = bands({ B04: 0.032, B06: 0.024, B08: 0.021, B11: 0.023 });
const floatingMaterial = bands({ B04: 0.041, B06: 0.04, B08: 0.0405, B11: 0.0346 });

describe("spectral indices", () => {
  it("keeps FDI near zero or negative for open water", () => {
    expect(floatingDebrisIndex(openWater)).toBeLessThan(0.005);
  });

  it("raises FDI above the water baseline for a mixed floating-material pixel", () => {
    expect(floatingDebrisIndex(floatingMaterial)).toBeGreaterThan(0.008);
    expect(floatingDebrisIndex(floatingMaterial)).toBeGreaterThan(floatingDebrisIndex(openWater));
  });

  it("follows the NDVI definition", () => {
    expect(normalizedDifferenceVegetationIndex(openWater)).toBeCloseTo(
      (0.021 - 0.032) / (0.021 + 0.032),
      10,
    );
  });

  it("computes FAI against the red–SWIR baseline", () => {
    const factor = (832.9 - 664.8) / (1612.05 - 664.8);
    expect(floatingAlgaeIndex(openWater)).toBeCloseTo(
      0.021 - (0.032 + (0.023 - 0.032) * factor),
      10,
    );
  });

  it("fails loudly when a required band is missing", () => {
    expect(() => floatingDebrisIndex(bands({ B04: 0.01, B08: 0.02 }))).toThrow(/B06/);
  });
});
