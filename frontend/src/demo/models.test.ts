import { describe, expect, it } from "vitest";
import { DEMO_MODEL_REPORT } from "./models";

const byThreshold = (threshold: number) => (point: { threshold: number }) =>
  Math.abs(point.threshold - threshold) < 1e-9;

describe("demo model report stays internally consistent", () => {
  it("marks exactly one model as the one in use", () => {
    expect(DEMO_MODEL_REPORT.models.filter((model) => model.inUse)).toHaveLength(1);
  });

  it("uses the five report classes for every confusion matrix", () => {
    for (const model of DEMO_MODEL_REPORT.models) {
      expect(model.confusion.labels).toEqual(DEMO_MODEL_REPORT.classes);
      expect(model.confusion.counts).toHaveLength(5);
      for (const row of model.confusion.counts) {
        expect(row).toHaveLength(5);
        expect(row.every((count) => Number.isInteger(count) && count >= 0)).toBe(true);
      }
    }
  });

  it("passes the PR curve through the operating point", () => {
    for (const model of DEMO_MODEL_REPORT.models) {
      const point = model.prCurve.find(byThreshold(model.threshold));
      expect(point).toBeDefined();
      expect(point?.precision).toBeCloseTo(model.metrics.precision, 2);
      expect(point?.recall).toBeCloseTo(model.metrics.recall, 2);
    }
  });

  it("keeps recall falling and precision rising as the threshold grows", () => {
    for (const model of DEMO_MODEL_REPORT.models) {
      const curve = [...model.prCurve].sort((a, b) => a.threshold - b.threshold);
      for (let index = 1; index < curve.length; index += 1) {
        expect(curve[index].recall).toBeLessThanOrEqual(curve[index - 1].recall);
        expect(curve[index].precision).toBeGreaterThanOrEqual(curve[index - 1].precision - 0.002);
      }
    }
  });

  it("derives F1 and IoU from precision and recall", () => {
    for (const { metrics } of DEMO_MODEL_REPORT.models) {
      const f1 = (2 * metrics.precision * metrics.recall) / (metrics.precision + metrics.recall);
      expect(metrics.f1).toBeCloseTo(f1, 3);
      expect(metrics.iou).toBeCloseTo(f1 / (2 - f1), 3);
    }
  });

  it("agrees with the confusion matrix on debris precision and recall", () => {
    for (const model of DEMO_MODEL_REPORT.models) {
      const counts = model.confusion.counts;
      const truePositive = counts[0][0];
      const labelled = counts[0].reduce((sum, value) => sum + value, 0);
      const predicted = counts.reduce((sum, row) => sum + row[0], 0);
      expect(truePositive / labelled).toBeCloseTo(model.metrics.recall, 2);
      expect(truePositive / predicted).toBeCloseTo(model.metrics.precision, 2);
      expect(labelled).toBe(DEMO_MODEL_REPORT.evaluationSet.positivePixels);
    }
  });

  it("brackets every metric with its 95 % interval", () => {
    for (const model of DEMO_MODEL_REPORT.models) {
      for (const key of ["f1", "iou", "precision", "recall"] as const) {
        const [low, high] = model.metricsCi95[key];
        expect(low).toBeLessThanOrEqual(model.metrics[key]);
        expect(high).toBeGreaterThanOrEqual(model.metrics[key]);
        expect(high - low).toBeLessThan(0.2);
      }
    }
  });

  it("matches the in-use model and threshold shown in the dossier copy", () => {
    const inUse = DEMO_MODEL_REPORT.models.find((model) => model.inUse);
    expect(inUse?.code).toBe("MariNeXt-S2");
    expect(inUse?.threshold).toBe(0.5);
    expect(inUse?.metrics.precision).toBe(0.74);
    expect(inUse?.metrics.recall).toBe(0.69);
  });
});
