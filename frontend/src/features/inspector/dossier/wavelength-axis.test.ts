import { describe, expect, it } from "vitest";
import { breakX, niceMax, wavelengthToX } from "./wavelength-axis";

const axis = { left: 30, width: 306, gap: 6 };

describe("broken wavelength axis", () => {
  it("gives 400–1000 nm 72 % of the plot and 1300–2300 nm the rest", () => {
    expect(wavelengthToX(400, axis)).toBe(30);
    expect(wavelengthToX(1000, axis)).toBeCloseTo(30 + 300 * 0.72, 5);
    expect(wavelengthToX(1300, axis)).toBeCloseTo(30 + 300 * 0.72 + 6, 5);
    expect(wavelengthToX(2300, axis)).toBeCloseTo(336, 5);
  });

  it("keeps wavelengths inside the break on the break line and clamps outside", () => {
    expect(wavelengthToX(1150, axis)).toBeCloseTo(breakX(axis), 5);
    expect(wavelengthToX(300, axis)).toBe(30);
    expect(wavelengthToX(2500, axis)).toBeCloseTo(336, 5);
  });

  it("is monotonic across bands", () => {
    const xs = [443, 490, 560, 665, 705, 740, 783, 842, 865, 945, 1375, 1610, 2190].map((nm) =>
      wavelengthToX(nm, axis),
    );
    expect(xs).toEqual([...xs].sort((a, b) => a - b));
  });

  it("rounds the reflectance ceiling up to a readable step", () => {
    expect(niceMax(0.094)).toBe(0.1);
    expect(niceMax(0.11)).toBe(0.12);
    expect(niceMax(0.61)).toBe(0.7);
  });
});
