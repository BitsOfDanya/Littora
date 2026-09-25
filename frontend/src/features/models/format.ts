import type { Interval } from "@/data/models";
import { formatNumber } from "@/lib/format/numbers";

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
