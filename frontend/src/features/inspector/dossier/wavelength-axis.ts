import type { Sentinel2BandId } from "@/domain/sentinel2";

export const BAND_WIDTH_NM: Readonly<Record<Sentinel2BandId, number>> = {
  B01: 21,
  B02: 66,
  B03: 36,
  B04: 31,
  B05: 15,
  B06: 15,
  B07: 20,
  B08: 106,
  B8A: 21,
  B09: 20,
  B10: 31,
  B11: 91,
  B12: 175,
};

export const AXIS_SEGMENTS = [
  { from: 400, to: 1000, share: 0.72 },
  { from: 1300, to: 2300, share: 0.28 },
] as const;

export type BrokenAxis = { left: number; width: number; gap: number };

export function wavelengthToX(nm: number, axis: BrokenAxis): number {
  const [near, far] = AXIS_SEGMENTS;
  const usable = axis.width - axis.gap;
  const nearWidth = usable * near.share;
  if (nm <= near.to) {
    const t = (Math.max(nm, near.from) - near.from) / (near.to - near.from);
    return axis.left + t * nearWidth;
  }
  if (nm < far.from) return axis.left + nearWidth + axis.gap / 2;
  const t = (Math.min(nm, far.to) - far.from) / (far.to - far.from);
  return axis.left + nearWidth + axis.gap + t * (usable - nearWidth);
}

export function breakX(axis: BrokenAxis): number {
  return axis.left + (axis.width - axis.gap) * AXIS_SEGMENTS[0].share + axis.gap / 2;
}

export function niceMax(value: number): number {
  const steps = [0.05, 0.1, 0.12, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5];
  return steps.find((step) => value <= step) ?? Math.ceil(value * 10) / 10;
}
