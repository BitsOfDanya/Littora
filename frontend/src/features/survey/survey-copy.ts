import type { SurveyScoreComponent } from "@/domain/survey";
import { formatNumber } from "@/lib/format/numbers";

export const COMPONENT_LABELS: Readonly<
  Record<SurveyScoreComponent, { short: string; full: string }>
> = {
  confidence: { short: "Увер.", full: "Уверенность" },
  coverage: { short: "Покр.", full: "Покрытие" },
  persistence: { short: "Уст.", full: "Устойчивость" },
  drift_risk: { short: "Дрейф", full: "Риск дрейфа" },
  uncertainty: { short: "Польза", full: "Польза проверки" },
  accessibility: { short: "Дост.", full: "Доступность" },
};

export const RANKING_RULE =
  "Порядок — по сводному баллу: уверенность, покрытие, устойчивость, риск дрейфа, польза проверки (неопределённость) и доступность";

export const METHOD_LABELS = { vessel: "судно", uav: "БПЛА", tasking: "дозаказ снимка" } as const;

const MONTHS_SHORT = [
  "янв",
  "фев",
  "мар",
  "апр",
  "мая",
  "июн",
  "июл",
  "авг",
  "сен",
  "окт",
  "ноя",
  "дек",
] as const;

export function windowLabel(from: string, to: string): string {
  const month = MONTHS_SHORT[Number(to.slice(5, 7)) - 1];
  return `${Number(from.slice(8, 10))}–${Number(to.slice(8, 10))} ${month}`;
}

export function hhmm(iso: string): string {
  return `${iso.slice(11, 16)}Z`;
}

export function formatScore(score: number): string {
  return formatNumber(score, 2);
}

export function formatKm(km: number): string {
  return `${formatNumber(km, km < 10 ? 1 : 0)} км`;
}

export function formatDuration(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = Math.round(minutes % 60);
  return hours ? `${hours} ч ${rest} мин` : `${rest} мин`;
}

export function targetsWord(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return "цель";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "цели";
  return "целей";
}
