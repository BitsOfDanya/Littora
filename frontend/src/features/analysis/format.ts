import { formatNumber } from "@/lib/format/numbers";
import { CONCENTRATION_UNIT } from "./analysis-copy";

export function formatConcentration(value: number | null): string {
  if (value === null) return "—";
  if (value >= 100) return formatNumber(value, 0);
  if (value >= 10) return formatNumber(value, 1);
  return formatNumber(value, 2);
}

export function concentrationWithUnit(value: number | null): string {
  return value === null ? "нет значения" : `${formatConcentration(value)} ${CONCENTRATION_UNIT}`;
}

export function formatDay(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}`;
}

export function formatDelta(days: number | null | undefined): string {
  if (days === null || days === undefined) return "дата неизвестна";
  if (days === 0) return "в день снимка";
  const sign = days > 0 ? "+" : "−";
  return `${sign}${Math.abs(days)} сут`;
}

const DAY_MS = 86_400_000;

export function dayOffset(fromIso: string, toIso: string): number {
  return Math.round((Date.parse(toIso.slice(0, 10)) - Date.parse(fromIso.slice(0, 10))) / DAY_MS);
}
