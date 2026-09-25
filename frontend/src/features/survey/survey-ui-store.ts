import { create } from "zustand";

export type SurveyOutcome =
  "confirmed_litter" | "other_material" | "natural" | "nothing_found" | "not_checked";

export const SURVEY_OUTCOMES: readonly { value: SurveyOutcome; label: string }[] = [
  { value: "confirmed_litter", label: "Подтверждён мусор" },
  { value: "other_material", label: "Другой материал" },
  { value: "natural", label: "Природное явление" },
  { value: "nothing_found", label: "Ничего не обнаружено" },
  { value: "not_checked", label: "Не проверено" },
];

type SurveyUiStore = {
  departureDate: string | null;
  outcomes: Readonly<Record<string, SurveyOutcome>>;
  setDepartureDate: (date: string) => void;
  saveOutcome: (targetId: string, outcome: SurveyOutcome) => void;
};

export const useSurveyUiStore = create<SurveyUiStore>()((set) => ({
  departureDate: null,
  outcomes: {},
  setDepartureDate: (departureDate) => set({ departureDate }),
  saveOutcome: (targetId, outcome) =>
    set((state) => ({ outcomes: { ...state.outcomes, [targetId]: outcome } })),
}));
