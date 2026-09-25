import { create } from "zustand";
import type { ResultStatus } from "@/lib/api/analyses";
import { useWorkspaceStore } from "./workspace-store";

export type AnalysisAreaMode = "aoi" | "view";

export type ObservationDates = "all" | "window";

export const WINDOW_DAYS = [0, 1, 3, 7] as const;

export type WindowDays = (typeof WINDOW_DAYS)[number];

type AnalysisStore = {
  analysisId: string | null;
  panelOpen: boolean;
  areaMode: AnalysisAreaMode;
  windowDays: WindowDays;
  targetKey: string | null;
  observationId: string | null;
  observationDates: ObservationDates;
  historyStatus: ResultStatus | null;
  historyAllAreas: boolean;
  setAnalysis: (analysisId: string | null) => void;
  setPanelOpen: (open: boolean) => void;
  setAreaMode: (mode: AnalysisAreaMode) => void;
  setWindowDays: (days: WindowDays) => void;
  setTarget: (key: string | null) => void;
  selectObservation: (observationId: string | null) => void;
  setObservationDates: (dates: ObservationDates) => void;
  setHistoryStatus: (status: ResultStatus | null) => void;
  setHistoryAllAreas: (all: boolean) => void;
};

export const useAnalysisStore = create<AnalysisStore>()((set) => ({
  analysisId: null,
  panelOpen: true,
  areaMode: "aoi",
  windowDays: 1,
  targetKey: null,
  observationId: null,
  observationDates: "all",
  historyStatus: null,
  historyAllAreas: false,
  setAnalysis: (analysisId) => set({ analysisId, panelOpen: true }),
  setPanelOpen: (panelOpen) => set({ panelOpen }),
  setAreaMode: (areaMode) => set({ areaMode }),
  setWindowDays: (windowDays) => set({ windowDays }),
  setTarget: (targetKey) => set({ targetKey }),
  selectObservation: (observationId) => set({ observationId }),
  setObservationDates: (observationDates) => set({ observationDates }),
  setHistoryStatus: (historyStatus) => set({ historyStatus }),
  setHistoryAllAreas: (historyAllAreas) => set({ historyAllAreas }),
}));

useWorkspaceStore.subscribe((state, previous) => {
  if (state.aoiId !== previous.aoiId)
    useAnalysisStore.setState({ analysisId: null, observationId: null });
});
