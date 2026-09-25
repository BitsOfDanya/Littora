import { create } from "zustand";
import type { BandReflectance } from "@/domain/detection";

export type PinnedSpectrum = { candidateId: string; bands: readonly BandReflectance[] };

const MAX_PINS = 3;

type SpectrumPinsStore = {
  pins: readonly PinnedSpectrum[];
  toggle: (pin: PinnedSpectrum) => void;
  clear: () => void;
};

export const useSpectrumPinsStore = create<SpectrumPinsStore>()((set) => ({
  pins: [],
  toggle: (pin) =>
    set((state) =>
      state.pins.some((entry) => entry.candidateId === pin.candidateId)
        ? { pins: state.pins.filter((entry) => entry.candidateId !== pin.candidateId) }
        : { pins: [...state.pins, pin].slice(-MAX_PINS) },
    ),
  clear: () => set({ pins: [] }),
}));
