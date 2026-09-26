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

export type SurveyPlanOptions = { speedKn: number; uavRangeKm: number; routeTargets: number };

export const DEFAULT_PLAN_OPTIONS: SurveyPlanOptions = {
  speedKn: 10,
  uavRangeKm: 15,
  routeTargets: 5,
};

export function planRequest(options: SurveyPlanOptions) {
  return {
    speed_kn: options.speedKn,
    uav_range_km: options.uavRangeKm,
    route_targets: options.routeTargets,
  };
}

type SurveyUiStore = {
  departureDate: string | null;
  outcomes: Readonly<Record<string, SurveyOutcome>>;
  options: SurveyPlanOptions;
  setDepartureDate: (date: string) => void;
  saveOutcome: (targetId: string, outcome: SurveyOutcome) => void;
  setOptions: (options: SurveyPlanOptions) => void;
};

export const useSurveyUiStore = create<SurveyUiStore>()((set) => ({
  departureDate: null,
  outcomes: {},
  options: DEFAULT_PLAN_OPTIONS,
  setDepartureDate: (departureDate) => set({ departureDate }),
  saveOutcome: (targetId, outcome) =>
    set((state) => ({ outcomes: { ...state.outcomes, [targetId]: outcome } })),
  setOptions: (options) => set({ options }),
}));
