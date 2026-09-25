import { create } from "zustand";
import { DEFAULT_AOI_ID, type AoiId } from "@/config/aois";
import { publicEnv } from "@/config/env";
import type { ForecastHorizonH } from "@/domain/forecast";

export type CompareMode = "swipe" | "opacity";

type CompareState = {
  beforeSceneId: string | null;
  afterSceneId: string | null;
  mode: CompareMode;
  position: number;
};

type WorkspaceStore = {
  aoiId: AoiId;
  sceneId: string | null;
  selectedCandidateId: string | null;
  selectedTargetId: string | null;
  compare: CompareState;
  forecastHorizonH: ForecastHorizonH;
  demoFixtures: boolean;
  setAoi: (aoiId: AoiId) => void;
  selectScene: (sceneId: string | null) => void;
  selectCandidate: (candidateId: string | null) => void;
  selectTarget: (targetId: string | null) => void;
  clearSelection: () => void;
  updateCompare: (patch: Partial<CompareState>) => void;
  setForecastHorizon: (horizonH: ForecastHorizonH) => void;
  setDemoFixtures: (enabled: boolean) => void;
  toggleDemoFixtures: () => void;
};

export const useWorkspaceStore = create<WorkspaceStore>()((set) => ({
  aoiId: DEFAULT_AOI_ID,
  sceneId: null,
  selectedCandidateId: null,
  selectedTargetId: null,
  compare: { beforeSceneId: null, afterSceneId: null, mode: "swipe", position: 0.5 },
  forecastHorizonH: 24,
  demoFixtures: publicEnv.demoFixtures,
  setAoi: (aoiId) =>
    set({ aoiId, sceneId: null, selectedCandidateId: null, selectedTargetId: null }),
  selectScene: (sceneId) => set({ sceneId }),
  selectCandidate: (selectedCandidateId) => set({ selectedCandidateId }),
  selectTarget: (selectedTargetId) => set({ selectedTargetId }),
  clearSelection: () => set({ selectedCandidateId: null, selectedTargetId: null }),
  updateCompare: (patch) => set((state) => ({ compare: { ...state.compare, ...patch } })),
  setForecastHorizon: (forecastHorizonH) => set({ forecastHorizonH }),
  setDemoFixtures: (demoFixtures) => set({ demoFixtures }),
  toggleDemoFixtures: () => set((state) => ({ demoFixtures: !state.demoFixtures })),
}));
