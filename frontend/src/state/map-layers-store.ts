import { create } from "zustand";
import { createJSONStorage, persist, type StateStorage } from "zustand/middleware";
import {
  type CompositeLayerId,
  DEFAULT_VISIBLE_LAYERS,
  type LayerId,
  type MapLayerId,
  resolveLayerId,
} from "@/config/layers";

export type BasemapId = "s2-mosaic" | "chart" | "bathymetry";

export type LayerLoadState = "loading" | "error";

type LayerFlags<T> = Readonly<Partial<Record<LayerId, T>>>;

type MapLayersStore = {
  basemapId: BasemapId;
  visible: LayerFlags<boolean>;
  opacity: LayerFlags<number>;
  composite: CompositeLayerId | null;
  particlesPaused: boolean;
  loadState: LayerFlags<LayerLoadState>;
  retryNonce: LayerFlags<number>;
  setBasemap: (basemapId: BasemapId) => void;
  toggleLayer: (layerId: MapLayerId) => void;
  setLayerVisible: (layerId: MapLayerId, visible: boolean) => void;
  setLayerOpacity: (layerId: MapLayerId, opacity: number) => void;
  setComposite: (composite: CompositeLayerId | null) => void;
  setParticlesPaused: (paused: boolean) => void;
  toggleParticlesPaused: () => void;
  setLayerLoadState: (layerId: MapLayerId, state: LayerLoadState | null) => void;
  retryLayer: (layerId: MapLayerId) => void;
};

type PersistedMapLayers = Pick<
  MapLayersStore,
  "basemapId" | "visible" | "opacity" | "composite" | "particlesPaused"
>;

export const safeLocalStorage: StateStorage = {
  getItem: (name) => {
    try {
      return window.localStorage.getItem(name);
    } catch {
      return null;
    }
  },
  setItem: (name, value) => {
    try {
      window.localStorage.setItem(name, value);
    } catch {
      return;
    }
  },
  removeItem: (name) => {
    try {
      window.localStorage.removeItem(name);
    } catch {
      return;
    }
  },
};

const DEFAULT_VISIBLE: LayerFlags<boolean> = Object.fromEntries(
  DEFAULT_VISIBLE_LAYERS.map((id) => [id, true]),
);

function withFlag<T>(flags: LayerFlags<T>, layerId: MapLayerId, value: T | null): LayerFlags<T> {
  const id = resolveLayerId(layerId);
  const next: Partial<Record<LayerId, T>> = { ...flags };
  if (value === null) delete next[id];
  else next[id] = value;
  return next;
}

function migrateVisible(
  stored: Readonly<Record<string, boolean>> | undefined,
): LayerFlags<boolean> {
  const visible: Partial<Record<LayerId, boolean>> = {};
  for (const [key, value] of Object.entries(stored ?? {}))
    visible[resolveLayerId(key as MapLayerId)] = value;
  return visible;
}

export const useMapLayersStore = create<MapLayersStore>()(
  persist(
    (set) => ({
      basemapId: "s2-mosaic",
      visible: DEFAULT_VISIBLE,
      opacity: {},
      composite: "scene-true-color",
      particlesPaused: false,
      loadState: {},
      retryNonce: {},
      setBasemap: (basemapId) => set({ basemapId }),
      toggleLayer: (layerId) =>
        set((state) => ({
          visible: withFlag(state.visible, layerId, !state.visible[resolveLayerId(layerId)]),
        })),
      setLayerVisible: (layerId, visible) =>
        set((state) => ({ visible: withFlag(state.visible, layerId, visible) })),
      setLayerOpacity: (layerId, opacity) =>
        set((state) => ({ opacity: withFlag(state.opacity, layerId, opacity) })),
      setComposite: (composite) => set({ composite }),
      setParticlesPaused: (particlesPaused) => set({ particlesPaused }),
      toggleParticlesPaused: () => set((state) => ({ particlesPaused: !state.particlesPaused })),
      setLayerLoadState: (layerId, loadState) =>
        set((state) => ({ loadState: withFlag(state.loadState, layerId, loadState) })),
      retryLayer: (layerId) =>
        set((state) => ({
          loadState: withFlag(state.loadState, layerId, "loading"),
          retryNonce: withFlag(
            state.retryNonce,
            layerId,
            (state.retryNonce[resolveLayerId(layerId)] ?? 0) + 1,
          ),
        })),
    }),
    {
      name: "littora.map-layers",
      version: 2,
      storage: createJSONStorage(() => safeLocalStorage),
      partialize: ({
        basemapId,
        visible,
        opacity,
        composite,
        particlesPaused,
      }): PersistedMapLayers => ({
        basemapId,
        visible,
        opacity,
        composite,
        particlesPaused,
      }),
      migrate: (persisted, version) => {
        const stored = (persisted ?? {}) as PersistedMapLayers;
        return version >= 2 ? stored : { ...stored, visible: migrateVisible(stored.visible) };
      },
      merge: (persisted, current) => {
        const stored = (persisted ?? {}) as Partial<PersistedMapLayers>;
        return { ...current, ...stored, visible: { ...DEFAULT_VISIBLE, ...stored.visible } };
      },
    },
  ),
);

export function useLayerVisible(layerId: MapLayerId): boolean {
  const id = resolveLayerId(layerId);
  return useMapLayersStore((state) => state.visible[id] ?? false);
}

export function useLayerOpacity(layerId: MapLayerId, fallback = 1): number {
  const id = resolveLayerId(layerId);
  return useMapLayersStore((state) => state.opacity[id] ?? fallback);
}

export function useLayerLoadState(layerId: MapLayerId): LayerLoadState | null {
  const id = resolveLayerId(layerId);
  return useMapLayersStore((state) => state.loadState[id] ?? null);
}

export function useLayerRetryNonce(layerId: MapLayerId): number {
  const id = resolveLayerId(layerId);
  return useMapLayersStore((state) => state.retryNonce[id] ?? 0);
}

export function useParticlesPaused(): boolean {
  return useMapLayersStore((state) => state.particlesPaused);
}
