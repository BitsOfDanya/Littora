import { describe, expect, it } from "vitest";
import { inkOpacity, prefersInverseText, rowNormalise } from "./confusion";

describe("confusion matrix helpers", () => {
  it("normalises each row to shares that sum to one", () => {
    const shares = rowNormalise([
      [69, 13, 9, 3, 6],
      [0, 0, 0, 0, 0],
    ]);
    expect(shares[0].reduce((sum, value) => sum + value, 0)).toBeCloseTo(1, 10);
    expect(shares[0][0]).toBeCloseTo(0.69, 10);
    expect(shares[1]).toEqual([0, 0, 0, 0, 0]);
  });

  it("maps shares to ink monotonically and leaves zero unfilled", () => {
    expect(inkOpacity(0)).toBe(0);
    expect(inkOpacity(0.02)).toBeGreaterThan(0.06);
    expect(inkOpacity(0.1)).toBeLessThan(inkOpacity(0.5));
    expect(inkOpacity(1)).toBeCloseTo(0.9, 10);
    expect(inkOpacity(2)).toBeCloseTo(0.9, 10);
  });

  it("switches to inverse text only on dark enough cells", () => {
    expect(prefersInverseText(0.13)).toBe(false);
    expect(prefersInverseText(0.69)).toBe(true);
  });
});
