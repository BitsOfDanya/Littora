import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { CoordinateFormat } from "@/lib/format/coordinates";
import { safeLocalStorage } from "./map-layers-store";

export type ThemeId = "night" | "day";

type PreferencesStore = {
  theme: ThemeId;
  coordinateFormat: CoordinateFormat;
  setTheme: (theme: ThemeId) => void;
  toggleTheme: () => void;
  setCoordinateFormat: (format: CoordinateFormat) => void;
  cycleCoordinateFormat: () => void;
};

type PersistedPreferences = Pick<PreferencesStore, "theme" | "coordinateFormat">;

const COORDINATE_FORMATS: readonly CoordinateFormat[] = ["dm", "dd", "dms"];

export const DEFAULT_COORDINATE_FORMAT: CoordinateFormat = "dm";

export const usePreferencesStore = create<PreferencesStore>()(
  persist(
    (set) => ({
      theme: "night",
      coordinateFormat: DEFAULT_COORDINATE_FORMAT,
      setTheme: (theme) => set({ theme }),
      toggleTheme: () => set((state) => ({ theme: state.theme === "night" ? "day" : "night" })),
      setCoordinateFormat: (coordinateFormat) => set({ coordinateFormat }),
      cycleCoordinateFormat: () =>
        set((state) => ({
          coordinateFormat:
            COORDINATE_FORMATS[
              (COORDINATE_FORMATS.indexOf(state.coordinateFormat) + 1) % COORDINATE_FORMATS.length
            ],
        })),
    }),
    {
      name: "littora.preferences",
      version: 2,
      storage: createJSONStorage(() => safeLocalStorage),
      partialize: ({ theme, coordinateFormat }): PersistedPreferences => ({
        theme,
        coordinateFormat,
      }),
      migrate: (persisted, version) => {
        const stored = (persisted ?? {}) as Partial<PersistedPreferences>;
        const theme: ThemeId = stored.theme === "day" ? "day" : "night";
        return version >= 2
          ? { theme, coordinateFormat: stored.coordinateFormat ?? DEFAULT_COORDINATE_FORMAT }
          : { theme, coordinateFormat: DEFAULT_COORDINATE_FORMAT };
      },
    },
  ),
);
