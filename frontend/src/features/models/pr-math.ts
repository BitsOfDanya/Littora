import type { PrCurvePoint } from "@/domain/model";

export type PrPoint = { precision: number; recall: number };

export const ISO_F1_LEVELS = [0.4, 0.6, 0.8] as const;

export function f1Score(precision: number, recall: number): number {
  return precision + recall > 0 ? (2 * precision * recall) / (precision + recall) : 0;
}

export function byThreshold(curve: readonly PrCurvePoint[]): PrCurvePoint[] {
  return [...curve].sort((a, b) => a.threshold - b.threshold);
}

export function thresholdRange(curve: readonly PrCurvePoint[]): readonly [number, number] {
  const sorted = byThreshold(curve);
  return [sorted[0]?.threshold ?? 0, sorted.at(-1)?.threshold ?? 1];
}

export function pointAtThreshold(curve: readonly PrCurvePoint[], threshold: number): PrCurvePoint {
  const sorted = byThreshold(curve);
  if (sorted.length === 0) return { threshold, precision: 0, recall: 0 };
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  if (threshold <= first.threshold) return { ...first, threshold: first.threshold };
  if (threshold >= last.threshold) return { ...last, threshold: last.threshold };
  const upperIndex = sorted.findIndex((point) => point.threshold >= threshold);
  const upper = sorted[upperIndex];
  const lower = sorted[upperIndex - 1];
  const span = upper.threshold - lower.threshold;
  const t = span > 0 ? (threshold - lower.threshold) / span : 0;
  return {
    threshold,
    precision: lower.precision + (upper.precision - lower.precision) * t,
    recall: lower.recall + (upper.recall - lower.recall) * t,
  };
}

export function thresholdNearestRecall(curve: readonly PrCurvePoint[], recall: number): number {
  let best = curve[0];
  if (!best) return 0.5;
  for (const point of curve) {
    if (Math.abs(point.recall - recall) < Math.abs(best.recall - recall)) best = point;
  }
  return best.threshold;
}

export function isoF1Curve(level: number, steps = 48): PrPoint[] {
  const start = level / (2 - level);
  return Array.from({ length: steps + 1 }, (_, index) => {
    const recall = start + ((1 - start) * index) / steps;
    return { recall, precision: (level * recall) / (2 * recall - level) };
  });
}

export function snapThreshold(value: number, step = 0.01): number {
  return Math.round(value / step) * step;
}
