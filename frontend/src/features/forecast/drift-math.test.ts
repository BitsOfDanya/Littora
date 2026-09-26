import { describe, expect, it } from "vitest";
import type { LngLat } from "@/domain/geo";
import { offsetLngLat } from "@/lib/geo/local-metric";
import {
  compassPoint,
  displacementOf,
  elapsedLabel,
  ellipseOf,
  horizonLabel,
  reliabilityHint,
  reliabilityOf,
  shiftIso,
  stepHorizon,
} from "./drift-math";

const ORIGIN: LngLat = [-88.24, 15.8];

function ellipseRing(semiEast: number, semiNorth: number, rotationDeg: number): GeoJSON.Polygon {
  const rotation = (rotationDeg * Math.PI) / 180;
  const ring = Array.from({ length: 96 }, (_, index) => {
    const angle = (index / 96) * Math.PI * 2;
    const x = Math.cos(angle) * semiEast;
    const y = Math.sin(angle) * semiNorth;
    return offsetLngLat(ORIGIN, [
      x * Math.cos(rotation) - y * Math.sin(rotation),
      x * Math.sin(rotation) + y * Math.cos(rotation),
    ]);
  });
  return { type: "Polygon", coordinates: [[...ring, ring[0]].map(([lng, lat]) => [lng, lat])] };
}

describe("drift math", () => {
  it("measures displacement and course from the origin", () => {
    const target = offsetLngLat(ORIGIN, [-8_000, -6_000]);
    const { distanceM, bearingDeg } = displacementOf(ORIGIN, target);
    expect(distanceM).toBeCloseTo(10_000, -1);
    expect(bearingDeg).toBeCloseTo(233.13, 1);
    expect(compassPoint(bearingDeg)).toBe("ЮЗ");
  });

  it("names the eight compass points", () => {
    expect([0, 44, 91, 136, 181, 224, 269, 316, 359].map(compassPoint)).toEqual([
      "С",
      "СВ",
      "В",
      "ЮВ",
      "Ю",
      "ЮЗ",
      "З",
      "СЗ",
      "С",
    ]);
  });

  it("recovers full axes, area and orientation of an ellipse polygon", () => {
    const summary = ellipseOf(ellipseRing(2_400, 1_500, 30));
    expect(summary.majorAxisM).toBeGreaterThan(4_750);
    expect(summary.majorAxisM).toBeLessThan(4_810);
    expect(summary.minorAxisM).toBeGreaterThan(2_960);
    expect(summary.minorAxisM).toBeLessThan(3_010);
    expect(summary.areaM2).toBeCloseTo(Math.PI * 2_400 * 1_500, -5);
    expect(summary.orientationDeg).toBeCloseTo(60, 0);
    const [dx, dy] = [summary.center[0] - ORIGIN[0], summary.center[1] - ORIGIN[1]];
    expect(Math.hypot(dx, dy)).toBeLessThan(1e-5);
  });

  it("grades reliability by lead time", () => {
    expect([6, 12, 24, 48, 72].map(reliabilityOf)).toEqual([
      "high",
      "high",
      "high",
      "medium",
      "low",
    ]);
  });

  it("leaves scenario reliability ungraded", () => {
    expect(reliabilityHint(24, true)).toBe("надёжность высокая");
    expect([6, 24, 72].map((hour) => reliabilityHint(hour, false))).toEqual(
      Array(3).fill("надёжность сценария не оценена"),
    );
  });

  it("formats horizons and elapsed time in Russian", () => {
    expect(horizonLabel(24)).toBe("+24 ч");
    expect(horizonLabel(-48)).toBe("−48 ч");
    expect(horizonLabel(0)).toBe("T₀");
    expect(elapsedLabel("2026-09-18T16:05:24Z", Date.parse("2026-09-19T00:10:00Z"))).toBe("T₀+8 ч");
    expect(elapsedLabel("2026-09-18T16:05:24Z", Date.parse("2026-09-25T17:30:00Z"))).toBe(
      "T₀+7 сут 1 ч",
    );
    expect(shiftIso("2026-09-18T16:05:24Z", 24)).toBe("2026-09-19T16:05:24.000Z");
  });

  it("clamps horizon steps to the ladder", () => {
    expect(stepHorizon(24, 1)).toBe(48);
    expect(stepHorizon(72, 1)).toBe(72);
    expect(stepHorizon(6, -1)).toBe(6);
  });
});
