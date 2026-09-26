import { create } from "zustand";

type ZoneFilter = { strict: boolean; toggle: () => void };

export const useZoneFilterStore = create<ZoneFilter>((set) => ({
  strict: false,
  toggle: () => set((state) => ({ strict: !state.strict })),
}));
