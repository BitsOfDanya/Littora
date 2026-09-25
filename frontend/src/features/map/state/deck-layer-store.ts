import type { Layer } from "@deck.gl/core";
import { create } from "zustand";

export type DeckLayerGroups = Record<string, readonly Layer[]>;

type DeckLayerStore = {
  groups: DeckLayerGroups;
  order: readonly string[];
  setGroup: (owner: string, layers: readonly Layer[]) => void;
  removeGroup: (owner: string) => void;
};

export const useDeckLayerStore = create<DeckLayerStore>()((set) => ({
  groups: {},
  order: [],
  setGroup: (owner, layers) =>
    set((state) => ({
      groups: { ...state.groups, [owner]: layers },
      order: state.order.includes(owner) ? state.order : [...state.order, owner],
    })),
  removeGroup: (owner) =>
    set((state) => {
      const groups = { ...state.groups };
      delete groups[owner];
      return { groups, order: state.order.filter((key) => key !== owner) };
    }),
}));

export function flattenDeckLayers(groups: DeckLayerGroups, order: readonly string[]): Layer[] {
  return order.flatMap((owner) => groups[owner] ?? []);
}
