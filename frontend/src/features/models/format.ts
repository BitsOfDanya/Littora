import type { Interval } from "@/data/models";
import { formatNumber, formatSigned } from "@/lib/format/numbers";

export const NARROW_NBSP = " ";

export const DASH = "—";

export function formatShare(value: number | null | undefined): string {
  return value === null || value === undefined || !Number.isFinite(value)
    ? DASH
    : formatNumber(value, 2);
}

export function formatInterval(interval: Interval | null | undefined): string {
  if (!interval) return DASH;
  return `${formatShare(interval[0])}–${formatShare(interval[1])}`;
}

export function formatCi95(interval: Interval | null | undefined): string {
  return `95${NARROW_NBSP}% ДИ ${formatInterval(interval)}`;
}

export function formatCount(value: number): string {
  return formatNumber(value).replace(/ /g, NARROW_NBSP);
}

export function formatValue(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined || !Number.isFinite(value)
    ? DASH
    : formatNumber(value, digits);
}

export function formatDifference(mean: number, interval: Interval, digits = 1): string {
  const [low, high] = interval;
  return `${formatSigned(mean, digits)} [${formatSigned(low, digits)}; ${formatSigned(high, digits)}]`;
}

export function formatPercentValue(ratio: number): string {
  const percent = ratio * 100;
  return formatNumber(percent, Number.isInteger(Math.round(percent * 10) / 10) ? 0 : 1);
}
