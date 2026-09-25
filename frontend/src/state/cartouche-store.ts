import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { LayerGroupId, MapModeId } from "@/config/layers";
import { safeLocalStorage } from "./map-layers-store";

export type CartoucheTab = "legend" | "objects";

export type CartoucheGroupId = LayerGroupId | "basemap";

type GroupOpenState = Readonly<Partial<Record<CartoucheGroupId, boolean>>>;

type CartoucheStore = {
  collapsedByMode: Readonly<Partial<Record<MapModeId, boolean>>>;
  groupOpenByMode: Readonly<Partial<Record<MapModeId, GroupOpenState>>>;
  autoCollapsed: boolean;
  tab: CartoucheTab;
  showAllLayers: boolean;
  tableFocusPending: boolean;
  setCollapsed: (mode: MapModeId, collapsed: boolean) => void;
  setAutoCollapsed: (autoCollapsed: boolean) => void;
  setGroupOpen: (mode: MapModeId, group: CartoucheGroupId, open: boolean) => void;
  setTab: (tab: CartoucheTab) => void;
  toggleShowAllLayers: () => void;
  requestTableFocus: () => void;
  consumeTableFocus: () => void;
};

type PersistedCartouche = Pick<CartoucheStore, "collapsedByMode" | "groupOpenByMode">;

export const useCartoucheStore = create<CartoucheStore>()(
  persist(
    (set) => ({
      collapsedByMode: {},
      groupOpenByMode: {},
      autoCollapsed: false,
      tab: "legend",
      showAllLayers: false,
      tableFocusPending: false,
      setCollapsed: (mode, collapsed) =>
        set((state) => ({ collapsedByMode: { ...state.collapsedByMode, [mode]: collapsed } })),
      setAutoCollapsed: (autoCollapsed) =>
        set((state) => (state.autoCollapsed === autoCollapsed ? state : { autoCollapsed })),
      setGroupOpen: (mode, group, open) =>
        set((state) => ({
          groupOpenByMode: {
            ...state.groupOpenByMode,
            [mode]: { ...state.groupOpenByMode[mode], [group]: open },
          },
        })),
      setTab: (tab) => set({ tab }),
      toggleShowAllLayers: () => set((state) => ({ showAllLayers: !state.showAllLayers })),
      requestTableFocus: () => set({ tab: "objects", tableFocusPending: true }),
      consumeTableFocus: () => set({ tableFocusPending: false }),
    }),
    {
      name: "littora.cartouche",
      version: 1,
      storage: createJSONStorage(() => safeLocalStorage),
      partialize: ({ collapsedByMode, groupOpenByMode }): PersistedCartouche => ({
        collapsedByMode,
        groupOpenByMode,
      }),
    },
  ),
);
