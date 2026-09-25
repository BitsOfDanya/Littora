import { create } from "zustand";
import type { CompareSide } from "./compare-model";

export type MosaicLoad = "loading" | "ready" | "error";

type CompareViewStore = {
  dividerLng: number | null;
  zoom: number;
  playing: boolean;
  activeSide: CompareSide;
  mosaicLoad: MosaicLoad;
  mosaicNonce: number;
  setView: (dividerLng: number, zoom: number) => void;
  setPlaying: (playing: boolean) => void;
  setActiveSide: (side: CompareSide) => void;
  setMosaicLoad: (state: MosaicLoad) => void;
  retryMosaic: () => void;
};

const LNG_EPSILON = 1e-7;
const ZOOM_EPSILON = 1e-3;

export const useCompareViewStore = create<CompareViewStore>()((set) => ({
  dividerLng: null,
  zoom: 0,
  playing: false,
  activeSide: "b",
  mosaicLoad: "loading",
  mosaicNonce: 0,
  setView: (dividerLng, zoom) =>
    set((state) =>
      state.dividerLng !== null &&
      Math.abs(state.dividerLng - dividerLng) < LNG_EPSILON &&
      Math.abs(state.zoom - zoom) < ZOOM_EPSILON
        ? state
        : { dividerLng, zoom },
    ),
  setPlaying: (playing) => set({ playing }),
  setActiveSide: (activeSide) => set({ activeSide }),
  setMosaicLoad: (mosaicLoad) =>
    set((state) => (state.mosaicLoad === mosaicLoad ? state : { mosaicLoad })),
  retryMosaic: () =>
    set((state) => ({ mosaicLoad: "loading", mosaicNonce: state.mosaicNonce + 1 })),
}));
