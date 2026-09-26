import { create } from "zustand";
import type { LngLat } from "@/domain/geo";

type RulerLine = {
  points: readonly LngLat[];
  cursor: LngLat | null;
  finished: boolean;
};

type RulerStore = RulerLine & {
  active: boolean;
  toggle: () => void;
  deactivate: () => void;
  addPoint: (point: LngLat) => void;
  setCursor: (cursor: LngLat | null) => void;
  finish: () => void;
  clear: () => void;
};

const EMPTY_LINE: RulerLine = { points: [], cursor: null, finished: false };

export const useRulerStore = create<RulerStore>()((set) => ({
  active: false,
  ...EMPTY_LINE,
  toggle: () => set((state) => ({ active: !state.active, ...EMPTY_LINE })),
  deactivate: () => set((state) => (state.active ? { active: false, ...EMPTY_LINE } : state)),
  addPoint: (point) =>
    set((state) =>
      state.finished
        ? { points: [point], cursor: null, finished: false }
        : { points: [...state.points, point] },
    ),
  setCursor: (cursor) =>
    set((state) => (state.cursor === cursor ? state : { cursor: state.finished ? null : cursor })),
  finish: () =>
    set((state) => (state.points.length < 2 ? EMPTY_LINE : { cursor: null, finished: true })),
  clear: () => set(EMPTY_LINE),
}));
