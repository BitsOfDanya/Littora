import type { BandReflectance } from "./detection";
import type { Sentinel2BandId } from "./sentinel2";

const WAVELENGTH_NM = { red: 664.8, nir: 832.9, swir1: 1612.05 } as const;
const FDI_SWIR_SCALE = 10;

type BandLookup = (band: Sentinel2BandId) => number;

function lookupFrom(bands: readonly BandReflectance[]): BandLookup {
  const values = new Map(bands.map((entry) => [entry.band, entry.reflectance]));
  return (band) => {
    const value = values.get(band);
    if (value === undefined) throw new Error(`Band ${band} is missing`);
    return value;
  };
}

const baselineFactor =
  (WAVELENGTH_NM.nir - WAVELENGTH_NM.red) / (WAVELENGTH_NM.swir1 - WAVELENGTH_NM.red);

export function floatingDebrisIndex(bands: readonly BandReflectance[]): number {
  const band = lookupFrom(bands);
  const baseline = band("B06") + (band("B11") - band("B06")) * baselineFactor * FDI_SWIR_SCALE;
  return band("B08") - baseline;
}

export function normalizedDifferenceVegetationIndex(bands: readonly BandReflectance[]): number {
  const band = lookupFrom(bands);
  return (band("B08") - band("B04")) / (band("B08") + band("B04"));
}

export function floatingAlgaeIndex(bands: readonly BandReflectance[]): number {
  const band = lookupFrom(bands);
  return band("B08") - (band("B04") + (band("B11") - band("B04")) * baselineFactor);
}

export function spectralIndices(bands: readonly BandReflectance[]) {
  return {
    fdi: floatingDebrisIndex(bands),
    ndvi: normalizedDifferenceVegetationIndex(bands),
    fai: floatingAlgaeIndex(bands),
  };
}
