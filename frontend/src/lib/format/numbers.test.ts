import { describe, expect, it } from "vitest";
import {
  formatArea,
  formatDistance,
  formatPercent,
  formatSigned,
  formatSignedPercent,
} from "./numbers";

const normalizeSpaces = (value: string) => value.replace(/[  ]/g, " ");

describe("number formatting", () => {
  it("uses comma decimals and a real minus sign", () => {
    expect(formatSigned(-1.25, 2)).toBe("−1,25");
    expect(formatSigned(4.1, 1)).toBe("+4,1");
  });

  it("formats percentages from ratios", () => {
    expect(formatPercent(0.214, 1)).toBe("21,4 %");
    expect(formatSignedPercent(-0.21)).toBe("−21 %");
  });

  it("switches area units at sensible thresholds", () => {
    expect(normalizeSpaces(formatArea(4_200))).toBe("4 200 м²");
    expect(formatArea(42_000)).toBe("0,042 км²");
    expect(formatArea(2_500_000)).toBe("2,50 км²");
  });

  it("switches distance units", () => {
    expect(formatDistance(850)).toBe("850 м");
    expect(formatDistance(2_300)).toBe("2,3 км");
    expect(formatDistance(17_500)).toBe("18 км");
  });
});
