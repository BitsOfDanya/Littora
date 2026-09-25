import type { CandidatePass } from "@/data/timeline";
import type { Estimate } from "@/domain/measurement";
import type { SceneSummary } from "@/domain/scene";
import { countRu, pluralRu } from "@/features/shell/orientation/plural";
import { formatNumber, formatPercent, formatSigned } from "@/lib/format/numbers";
import { formatLongDate } from "@/lib/format/time";
import type { CompareInterval } from "./compare-model";

const NBSP = " ";

export function formatKm2(areaM2: number): string {
  const km2 = areaM2 / 1_000_000;
  return formatNumber(km2, km2 < 0.1 ? 3 : 2);
}

export function formatCoverage(ratio: number): string {
  const percent = Math.round(ratio * 1000) / 10;
  return formatNumber(percent, Number.isInteger(percent) ? 0 : 1);
}

export function formatCoverageInterval(estimate: Estimate): string {
  return `${formatCoverage(estimate.low)}–${formatCoverage(estimate.high)}`;
}

export function formatPp(points: number, digits = 1): string {
  return `${formatSigned(points, digits)}${NBSP}п.${NBSP}п.`;
}

export function cloudText(scene: SceneSummary): string {
  return `облачно ${formatPercent(scene.cloudCover)}`;
}

export function passStateText(pass: CandidatePass | null | undefined, scene: SceneSummary): string {
  if (!pass || pass.state === "no-data")
    return `нет данных · облачность ${formatPercent(scene.cloudCover)}`;
  if (pass.state === "cloudy") return cloudText(scene);
  if (pass.state === "not-found") return "не найдено";
  return pass.coverage ? `найдено · ${formatCoverage(pass.coverage.value)}${NBSP}%` : "найдено";
}

export function intervalText(interval: CompareInterval): string {
  const between = countRu(interval.between, ["пролёт", "пролёта", "пролётов"]);
  const usable = interval.usableBetween
    ? `пригодных ${interval.usableBetween}`
    : interval.between
      ? "пригодных нет"
      : "";
  const parts = [
    `Интервал ${interval.days}${NBSP}сут`,
    interval.between ? `между датами ${between}${usable ? `, ${usable}` : ""}` : "соседние пролёты",
  ];
  if (interval.reversed) parts.push("B раньше A");
  return parts.join(" · ");
}

export function sceneAccessibleName(letter: "A" | "B", scene: SceneSummary): string {
  return `Дата ${letter}: ${formatLongDate(scene.acquiredAt)}, ${scene.platform}, облачность ${formatPercent(scene.cloudCover)}`;
}

export function objectsCount(count: number): string {
  return `${count} ${pluralRu(count, ["объект", "объекта", "объектов"])}`;
}
