import type { ResultStatus } from "@/lib/api/analyses";
import type { StatusTone } from "@/ui/status-tag";

export const CONCENTRATION_UNIT = "шт./км²";

export const STATUS_LABELS: Record<ResultStatus, string> = {
  detected: "обнаружено",
  not_detected: "не обнаружено",
  insufficient_data: "недостаточно данных",
  research_estimate: "исследовательская оценка",
  concentration_unavailable: "концентрация недоступна",
};

export const STATUS_TONES: Record<ResultStatus, StatusTone> = {
  detected: "alarm",
  not_detected: "ok",
  insufficient_data: "caution",
  research_estimate: "info",
  concentration_unavailable: "neutral",
};

export const STATUS_HINTS: Record<ResultStatus, string> = {
  detected: "модель нашла зоны плавающего мусора на снимке",
  not_detected: "снимок пригоден, модель зон мусора не нашла",
  insufficient_data:
    "вывода нет: снимок непригоден, район не подходит детектору или модель не подключена",
  research_estimate: "значение получено, но перенос на снимки не подтверждён",
  concentration_unavailable: "значение шт./км² по снимку не выдаётся",
};

export const RESULT_STATUS_ORDER: readonly ResultStatus[] = [
  "detected",
  "not_detected",
  "insufficient_data",
  "research_estimate",
  "concentration_unavailable",
];

export const QUALITY_CLASSES = [
  { key: "water", label: "вода", color: "rgba(64, 132, 170, 0.55)" },
  { key: "cloud", label: "облака", color: "rgba(250, 250, 250, 0.9)" },
  { key: "shadow", label: "тени", color: "rgba(30, 34, 52, 0.8)" },
  { key: "land", label: "суша", color: "rgba(118, 108, 86, 0.75)" },
  { key: "snow", label: "снег и лёд", color: "rgba(170, 225, 250, 0.75)" },
  { key: "nodata", label: "нет данных", color: "rgba(40, 40, 40, 0.85)" },
  { key: "other", label: "прочее", color: "rgba(150, 150, 150, 0.6)" },
] as const;

export const BRIGHT_WATER = {
  label: "яркая вода: блик, пена или плавающий материал",
  color: "rgba(255, 196, 110, 0.85)",
} as const;

export const MEASUREMENT_NOTE = "Натурные данные кейса — измерение с судна, не результат модели";

export const PROFILE_LABELS: Readonly<Record<string, string>> = {
  S1_trawl_5_to_50: "трал, 5–50 см",
  S1_trawl_GT5_N: "трал, > 5 см, сети и канаты",
  S1_trawl_GT5_H: "трал, > 5 см, жёсткий пластик и плёнка",
  S1_trawl_GT5_F: "трал, > 5 см, пенопласт",
  S1_aerial_GT50: "авиасъёмка, > 50 см",
  S2_visual_GT2: "визуальный учёт с судна, > 2 см",
  S3_visual_GT2: "визуальный учёт с судна, > 2 см",
  S4_visual_GT2_5: "визуальный учёт с судна, > 2,5 см",
};

export function profileLabel(profile: string): string {
  return PROFILE_LABELS[profile] ?? profile;
}
