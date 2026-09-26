import type { DriftState } from "@/data/drift";
import type { BeachSegmentRisk, DriftForecastDetail, ProbabilityEstimate } from "@/data/forecast";
import type { DriftEnvelope, ForecastHorizonH } from "@/domain/forecast";
import { formatNumber } from "@/lib/format/numbers";
import { compassPoint, ellipseOf, horizonLabel } from "./drift-math";
import { horizonRow, topSource } from "./forecast-model";

const NNBSP = " ";

export const SCENARIO_NOTE = "сценарий дрейфа, не проверен на дрифтерах";

export type DriftStateCopy = { title: string; detail: string };

export function formatProbability(value: number): string {
  return formatNumber(value, 2);
}

export function formatEstimate(estimate: ProbabilityEstimate): string {
  return `${formatProbability(estimate.value)} (${formatProbability(estimate.low)}–${formatProbability(estimate.high)})`;
}

export function formatKm(meters: number): string {
  if (meters < 1_000) return `${formatNumber(Math.round(meters / 10) * 10)}${NNBSP}м`;
  return `${formatNumber(meters / 1_000, 1)}${NNBSP}км`;
}

export function formatKm2(squareMeters: number): string {
  const km2 = squareMeters / 1_000_000;
  return `${formatNumber(km2, km2 < 10 ? 1 : 0)}${NNBSP}км²`;
}

export function formatCourse(bearingDeg: number): string {
  return `${compassPoint(bearingDeg)} ${formatNumber(bearingDeg)}°`;
}

export function formatAxes(majorM: number, minorM: number): string {
  return `${formatNumber(majorM / 1_000, 1)} × ${formatNumber(minorM / 1_000, 1)}${NNBSP}км`;
}

export function formatWindow([from, to]: readonly [number, number]): string {
  return from === to ? `через ${from}${NNBSP}ч` : `через ${from}–${to}${NNBSP}ч`;
}

export function envelopeHint(envelope: DriftEnvelope): string {
  const ellipse = ellipseOf(envelope.polygon);
  return `Облако ${horizonLabel(envelope.horizonH)} · ${formatNumber(Math.round(envelope.probability * 100))}${NNBSP}% ансамбля · ${formatAxes(ellipse.majorAxisM, ellipse.minorAxisM)} — щелчок: выбрать горизонт`;
}

export function horizonHint(forecast: DriftForecastDetail, horizonH: ForecastHorizonH): string {
  const row = horizonRow(forecast, horizonH);
  if (!row) return horizonLabel(horizonH);
  return `${horizonLabel(horizonH)} · медиана · ${formatKm(row.displacement.distanceM)} ${formatCourse(row.displacement.bearingDeg)} — щелчок: выбрать горизонт`;
}

export function beachingHint(risk: BeachSegmentRisk): string {
  return `${risk.name} — вынос на берег ${formatWindow(risk.windowH)} · ${formatEstimate(risk.probability)}`;
}

export function hindcastText(
  forecast: DriftForecastDetail,
  lowerFirst: (text: string) => string,
): string {
  const source = topSource(forecast);
  const lead = `${horizonLabel(-forecast.hindcastPath.length + 1)}`;
  if (!source) return `${lead} · источник не определён`;
  return `${lead} · вероятный источник: ${lowerFirst(source.name)} · ${formatProbability(source.probability.value)}`;
}

export function upperFirst(text: string): string {
  return text.charAt(0).toLocaleUpperCase("ru") + text.slice(1);
}

export function driftStateCopy(state: DriftState): DriftStateCopy | null {
  switch (state.status) {
    case "no-analysis":
      return {
        title: "Нет анализа района",
        detail:
          "сценарий строится от зон детектора: запустите в «Мониторинге» анализ, где найдены зоны, и нажмите «Сценарий дрейфа»",
      };
    case "loading":
      return { title: "Загружаем дрейф…", detail: "зоны анализа и сохранённый сценарий" };
    case "no-zones":
      return {
        title: "Нет зон детектора для дрейфа",
        detail: state.reason ?? "в выбранном анализе детектор не выделил ни одной зоны",
      };
    case "absent":
      return {
        title: "Дрейф не рассчитан",
        detail: "ветер, волны и течения Open-Meteo от момента снимка",
      };
    case "computing":
      return {
        title: "Считаем сценарий дрейфа…",
        detail: "загружаем ветер, волны и течения Open-Meteo",
      };
    case "failed":
      return { title: "Дрейф не получен", detail: state.message };
    case "unavailable":
      return { title: upperFirst(state.label), detail: state.reason };
    default:
      return null;
  }
}
