import { create } from "zustand";

type ForecastUiStore = {
  playing: boolean;
  setPlaying: (playing: boolean) => void;
  togglePlaying: () => void;
};

export const useForecastUiStore = create<ForecastUiStore>()((set) => ({
  playing: false,
  setPlaying: (playing) => set({ playing }),
  togglePlaying: () => set((state) => ({ playing: !state.playing })),
}));
