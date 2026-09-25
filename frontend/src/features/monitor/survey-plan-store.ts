import { create } from "zustand";

export type SurveyPlanEntry = { candidateId: string; addedAt: string; actor: string };

type SurveyPlanStore = {
  entries: readonly SurveyPlanEntry[];
  add: (candidateId: string, at?: Date) => boolean;
  remove: (candidateId: string) => void;
  toggle: (candidateId: string) => void;
};

export const SURVEY_PLAN_ACTOR = "оператор";

export const useSurveyPlanStore = create<SurveyPlanStore>()((set, get) => ({
  entries: [],
  add: (candidateId, at = new Date()) => {
    if (get().entries.some((entry) => entry.candidateId === candidateId)) return false;
    set((state) => ({
      entries: [
        ...state.entries,
        { candidateId, addedAt: at.toISOString(), actor: SURVEY_PLAN_ACTOR },
      ],
    }));
    return true;
  },
  remove: (candidateId) =>
    set((state) => ({
      entries: state.entries.filter((entry) => entry.candidateId !== candidateId),
    })),
  toggle: (candidateId) => {
    const { entries, add, remove } = get();
    if (entries.some((entry) => entry.candidateId === candidateId)) remove(candidateId);
    else add(candidateId);
  },
}));

export function useSurveyPlanEntry(candidateId: string | null): SurveyPlanEntry | undefined {
  return useSurveyPlanStore((state) =>
    candidateId ? state.entries.find((entry) => entry.candidateId === candidateId) : undefined,
  );
}
