import type { ConfidenceClass, LookAlike, ReviewStatus, SurveyPriority } from "@/domain/detection";

export const CONFIDENCE_LABEL: Record<ConfidenceClass, string> = {
  likely: "высокая",
  possible: "средняя",
  low: "низкая",
};

export const REVIEW_STATUS_LABEL: Record<ReviewStatus, string> = {
  unreviewed: "Не проверено",
  needs_survey: "Нужна проверка",
  confirmed_litter: "Подтверждён мусор",
  other_material: "Другой материал",
  natural: "Природное явление",
  nothing_found: "Ничего не обнаружено",
};

export const PRIORITY_LABEL: Record<SurveyPriority, string> = {
  high: "Высокий",
  medium: "Средний",
  low: "Низкий",
};

export const LOOK_ALIKE_LABEL: Record<LookAlike, string> = {
  sargassum: "Саргассум",
  foam: "Пена",
  ship_wake: "Судовой след",
  cloud_edge: "Край облака",
  sun_glint: "Солнечный блик",
  turbid_water: "Мутная вода",
};
