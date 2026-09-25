import { describe, expect, it } from "vitest";
import {
  formatTickLabel,
  MIN_MAJOR_SPACING_PX,
  MIN_MINOR_SPACING_PX,
  pixelsPerLongitudeMinute,
  tickDegrees,
  tickIndexRange,
  tickSpecFor,
} from "./ticks";

describe("tickSpecFor", () => {
  it.each([6.8, 8.6, 10.3, 13.2])("keeps minor ≥ 7 px and major ≥ 70 px at z %s", (zoom) => {
    const { minorMinutes, majorMinutes } = tickSpecFor(zoom);
    const spacing = pixelsPerLongitudeMinute(zoom);
    expect(minorMinutes * spacing).toBeGreaterThanOrEqual(MIN_MINOR_SPACING_PX);
    expect(majorMinutes * spacing).toBeGreaterThanOrEqual(MIN_MAJOR_SPACING_PX);
    expect(Math.round(majorMinutes * 10) % Math.round(minorMinutes * 10)).toBe(0);
  });

  it("uses 1′ chequer and 5′ labels at the Gulf of Honduras working zoom", () => {
    expect(tickSpecFor(10.3)).toEqual({ minorMinutes: 1, majorMinutes: 5 });
  });
});

describe("tickIndexRange", () => {
  it("returns the 88°40′ tick for a western span", () => {
    const [first, last] = tickIndexRange(-88.7, -88.6, 5);
    expect([first, last]).toEqual([-1064, -1064]);
    expect(tickDegrees(first, 5)).toBeCloseTo(-(88 + 40 / 60), 9);
  });

  it("is independent of argument order", () => {
    expect(tickIndexRange(16.1, 15.7, 1)).toEqual(tickIndexRange(15.7, 16.1, 1));
  });
});

describe("formatTickLabel", () => {
  it("prints whole degrees without minutes", () => {
    expect(formatTickLabel(16, false)).toBe("16°");
    expect(formatTickLabel(-88, true)).toBe("88°");
  });

  it("prints minutes with or without degrees", () => {
    expect(formatTickLabel(15 + 55 / 60, false)).toBe("55′");
    expect(formatTickLabel(-(88 + 5 / 60), true)).toBe("88°05′");
  });

  it("keeps one decimal for sub-minute ticks", () => {
    expect(formatTickLabel(15 + 52.5 / 60, true)).toBe("15°52,5′");
  });
});
