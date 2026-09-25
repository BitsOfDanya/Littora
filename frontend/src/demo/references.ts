import type { BandReflectance } from "@/domain/detection";
import { OPEN_WATER, toBands, turbidWater } from "./spectra";

export type ReferenceSpectrumKey = "plastic" | "sargassum" | "foam" | "water";

export type ReferenceSpectrum = {
  key: ReferenceSpectrumKey;
  label: string;
  source: string;
  endMember: readonly BandReflectance[];
};

const PLASTIC_PLP = [0.082, 0.088, 0.094, 0.09, 0.104, 0.118, 0.142, 0.171, 0.162, 0.094, 0.061];
const SARGASSUM = [0.031, 0.036, 0.058, 0.041, 0.088, 0.176, 0.208, 0.226, 0.218, 0.086, 0.041];
const SEA_FOAM = [0.246, 0.258, 0.251, 0.221, 0.204, 0.188, 0.179, 0.171, 0.166, 0.082, 0.051];

export const DEMO_REFERENCE_SPECTRA: readonly ReferenceSpectrum[] = [
  {
    key: "plastic",
    label: "Пластик (PLP)",
    source: "иллюстрация по мотивам Plastic Litter Project 2021",
    endMember: toBands(PLASTIC_PLP),
  },
  {
    key: "sargassum",
    label: "Саргассум",
    source: "иллюстрация по мотивам MARIDA, класс Sargassum",
    endMember: toBands(SARGASSUM),
  },
  {
    key: "foam",
    label: "Пена",
    source: "иллюстрация по мотивам MARIDA, класс Foam",
    endMember: toBands(SEA_FOAM),
  },
  {
    key: "water",
    label: "Вода",
    source: "чистая вода вокруг пятна",
    endMember: toBands(OPEN_WATER),
  },
];

export function referenceAtCoverage(
  reference: ReferenceSpectrum,
  coverage: number,
  turbidity = 0,
): BandReflectance[] {
  const water = turbidWater(turbidity);
  if (reference.key === "water") return toBands(water);
  return toBands(
    water.map(
      (value, index) => value * (1 - coverage) + reference.endMember[index].reflectance * coverage,
    ),
  );
}
