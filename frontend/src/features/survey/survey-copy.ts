import type { SurveyState } from "@/data/survey";
import type { SurveyScoreComponent } from "@/domain/survey";
import { upperFirst } from "@/features/forecast/forecast-copy";
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
  if (from === to) return `${Number(to.slice(8, 10))} ${month}`;
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

export const NOT_ASSESSED = "не оценивается";

export const API_RANKING_RULE =
  "Порядок — по сводному баллу: вероятность детектора, площадь, срочность по дрейфу, польза проверки и близость к порту; устойчивость по одному снимку не оценивается";

export const PLAN_NOTE =
  "расчётный план: маршрут в обход суши по маске воды снимка или дрейфа, где маски нет — по прямой; погода и допуски судна не учтены";

export const URGENCY_LABELS = {
  high: "высокая",
  medium: "средняя",
  low: "низкая",
  unknown: "не оценена",
} as const;

export const SPEED_OPTIONS_KN = [6, 10, 15, 20] as const;

export const UAV_RANGE_OPTIONS_KM = [5, 10, 15, 25] as const;

export const ROUTE_TARGET_OPTIONS = [3, 5, 8] as const;

export function stampLabel(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)} ${hhmm(iso)}`;
}

export function spanLabel(fromIso: string, toIso: string): string {
  const sameDay = fromIso.slice(0, 10) === toIso.slice(0, 10);
  return sameDay
    ? `${stampLabel(fromIso)}–${hhmm(toIso)}`
    : `${stampLabel(fromIso)} – ${stampLabel(toIso)}`;
}

export function elapsedLabel(days: number): string {
  if (days < 2) return `${formatNumber(Math.round(days * 24))} ч`;
  return `${formatNumber(Math.round(days))} сут`;
}

export function formatHoursShort(hours: number): string {
  return `${formatNumber(hours, hours < 10 && !Number.isInteger(hours) ? 1 : 0)} ч`;
}

export type SurveyStateCopy = { title: string; detail: string };

export function surveyStateCopy(state: SurveyState): SurveyStateCopy | null {
  switch (state.status) {
    case "no-analysis":
      return {
        title: "Нет анализа района",
        detail: "план строится по зонам детектора — запустите анализ в «Мониторинге»",
      };
    case "loading":
      return { title: "Загружаем план…", detail: "зоны анализа и сохранённый план обследования" };
    case "no-zones":
      return {
        title: "Нет зон для обследования",
        detail: state.reason ?? "в выбранном анализе детектор не выделил ни одной зоны",
      };
    case "absent":
      return {
        title: "План обследования не построен",
        detail:
          "цели из зон детектора, маршрут от ближайшего порта World Port Index, окно выхода по светлому времени",
      };
    case "building":
      return { title: "Строим план…", detail: "ранжируем зоны, ищем порт, маршрут и окно выхода" };
    case "failed":
      return { title: "План не получен", detail: state.message };
    case "unavailable":
      return { title: upperFirst(state.label), detail: state.reason };
    default:
      return null;
  }
}

export const DRIFT_HINT =
  "Для срочности и окон по времени сначала рассчитайте дрейф в «Прогнозе» — план учтёт его при перестроении.";
