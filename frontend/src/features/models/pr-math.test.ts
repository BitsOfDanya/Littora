import { describe, expect, it } from "vitest";
import {
  f1Score,
  isoF1Curve,
  pointAtThreshold,
  snapThreshold,
  thresholdNearestRecall,
  thresholdRange,
} from "./pr-math";

const CURVE = [
  { threshold: 0.7, precision: 0.9, recall: 0.4 },
  { threshold: 0.3, precision: 0.5, recall: 0.9 },
  { threshold: 0.5, precision: 0.74, recall: 0.69 },
];

describe("PR curve maths", () => {
  it("returns the stored point exactly at a curve threshold", () => {
    expect(pointAtThreshold(CURVE, 0.5)).toEqual({ threshold: 0.5, precision: 0.74, recall: 0.69 });
  });

  it("interpolates linearly between the bracketing thresholds", () => {
    const point = pointAtThreshold(CURVE, 0.6);
    expect(point.precision).toBeCloseTo(0.82, 6);
    expect(point.recall).toBeCloseTo(0.545, 6);
  });

  it("clamps outside the evaluated threshold range", () => {
    expect(pointAtThreshold(CURVE, 0.05)).toMatchObject({ threshold: 0.3, recall: 0.9 });
    expect(pointAtThreshold(CURVE, 0.99)).toMatchObject({ threshold: 0.7, recall: 0.4 });
    expect(thresholdRange(CURVE)).toEqual([0.3, 0.7]);
  });

  it("picks the threshold whose recall is nearest to the pointer", () => {
    expect(thresholdNearestRecall(CURVE, 0.66)).toBe(0.5);
    expect(thresholdNearestRecall(CURVE, 0.1)).toBe(0.7);
  });

  it("computes F1 as the harmonic mean and survives zeros", () => {
    expect(f1Score(0.74, 0.69)).toBeCloseTo(0.714, 3);
    expect(f1Score(0, 0)).toBe(0);
  });

  it("draws iso-F1 guides that keep F1 constant inside the unit square", () => {
    for (const level of [0.4, 0.6, 0.8]) {
      const points = isoF1Curve(level, 12);
      expect(points[0].precision).toBeCloseTo(1, 6);
      expect(points.at(-1)?.recall).toBeCloseTo(1, 6);
      for (const point of points) {
        expect(f1Score(point.precision, point.recall)).toBeCloseTo(level, 6);
        expect(point.precision).toBeLessThanOrEqual(1 + 1e-9);
      }
    }
  });

  it("snaps slider values to the curve step without float noise", () => {
    expect(snapThreshold(0.4999999)).toBeCloseTo(0.5, 10);
    expect(snapThreshold(0.123)).toBeCloseTo(0.12, 10);
  });
});
