import { describe, expect, it } from "vitest";
import { ageLabel, nearestIndex, spreadMarks } from "./rail-model";
import { clampWindow, DAY, panWindow, zoomWindow } from "./time-scale";

describe("rail marks", () => {
  it("pushes marks that share a moment apart by one step, keeping order", () => {
    const placed = spreadMarks([0.5, 0.1, 0.5001], (value) => value, 1000, 12);
    expect(placed.map((entry) => entry.item)).toEqual([0.1, 0.5, 0.5001]);
    expect(placed[0].offsetPx).toBe(0);
    expect(placed[1].offsetPx).toBe(0);
    expect(placed[2].offsetPx).toBeCloseTo(11.9, 5);
  });

  it("finds the nearest usable pass on either side", () => {
    const passes = ["usable", "unusable", "unusable", "partial", "usable"];
    expect(nearestIndex(passes, 2, (value) => value === "usable")).toBe(0);
    expect(nearestIndex(passes, 3, (value) => value === "usable")).toBe(4);
    expect(nearestIndex(["unusable"], 0, (value) => value === "usable")).toBe(-1);
  });

  it("writes the observation age in days", () => {
    const now = Date.parse("2026-09-25T16:12:00Z");
    expect(ageLabel("2026-09-18T16:05:24Z", now)).toBe("7 сут назад");
    expect(ageLabel("2026-09-24T10:12:00Z", now)).toBe("1 сут 6 ч назад");
    expect(ageLabel("2026-09-25T12:12:00Z", now)).toBe("4 ч назад");
  });
});

describe("time window", () => {
  const window = { start: 0, end: 40 * DAY };

  it("zooms around the anchor", () => {
    const zoomed = zoomWindow(window, 10 * DAY, 0.5);
    expect(zoomed.end - zoomed.start).toBe(20 * DAY);
    expect(zoomed.start).toBe(5 * DAY);
  });

  it("never zooms below the minimum span", () => {
    const zoomed = zoomWindow(window, 10 * DAY, 0.01);
    expect(zoomed.end - zoomed.start).toBe(6 * DAY);
  });

  it("pans by a share of the span and clamps to the bounds", () => {
    const panned = panWindow({ start: 10 * DAY, end: 20 * DAY }, 5);
    expect(clampWindow(panned, window)).toEqual({ start: 30 * DAY, end: 40 * DAY });
  });
});
