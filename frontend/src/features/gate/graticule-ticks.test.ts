import { describe, expect, it } from "vitest";
import { chequerParity, planTicks, tickLabel, ticksInRange } from "./graticule-ticks";

describe("graticule ticks", () => {
  it("keeps minor ticks at least 7 px and labelled majors at least 70 px apart", () => {
    expect(planTicks(9.2)).toEqual({ minorMin: 1, majorMin: 10 });
    expect(planTicks(2.5)).toEqual({ minorMin: 5, majorMin: 30 });
    expect(planTicks(0.05)).toEqual({ minorMin: 300, majorMin: 300 });
  });

  it("keeps majors a multiple of minors", () => {
    expect(planTicks(3)).toEqual({ minorMin: 5, majorMin: 30 });
    expect(planTicks(4)).toEqual({ minorMin: 2, majorMin: 30 });
  });

  it("lists ticks inside the range in minutes", () => {
    expect(ticksInRange(-88.5, -88.2, 10)).toEqual([-5310, -5300]);
    expect(ticksInRange(16.2, 16, 5)).toEqual([960, 965, 970]);
  });

  it("labels whole degrees and minutes", () => {
    expect(tickLabel(-88 * 60)).toEqual({ text: "88°", degree: true });
    expect(tickLabel(-88 * 60 - 10)).toEqual({ text: "10′", degree: false });
    expect(tickLabel(16 * 60 + 5)).toEqual({ text: "05′", degree: false });
  });

  it("alternates chequer blocks for negative and positive minutes", () => {
    expect(chequerParity(-2, 1)).toBe(0);
    expect(chequerParity(-1, 1)).toBe(1);
    expect(chequerParity(3, 1)).toBe(1);
  });
});
