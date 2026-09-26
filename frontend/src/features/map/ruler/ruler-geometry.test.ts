import { describe, expect, it } from "vitest";
import type { LngLat } from "@/domain/geo";
import {
  EARTH_RADIUS_KM,
  formatRulerDistance,
  greatCirclePath,
  haversineMeters,
  interpolateGreatCircle,
  rulerSegments,
  totalMeters,
} from "./ruler-geometry";

const DEGREE_M = (Math.PI / 180) * EARTH_RADIUS_KM * 1000;

describe("haversineMeters", () => {
  it("is zero for the same point", () => {
    expect(haversineMeters([37.6, 44.7], [37.6, 44.7])).toBe(0);
  });

  it("gives one degree of arc along a meridian", () => {
    expect(haversineMeters([37, 44], [37, 45])).toBeCloseTo(DEGREE_M, 3);
  });

  it("shrinks parallels by the cosine of latitude", () => {
    const along = haversineMeters([30, 60], [30.01, 60]);
    expect(along / (0.01 * DEGREE_M)).toBeCloseTo(Math.cos(Math.PI / 3), 4);
  });

  it("is symmetric and crosses the antimeridian the short way", () => {
    const east = haversineMeters([179.5, 65], [-179.5, 65]);
    expect(east).toBeCloseTo(haversineMeters([-179.5, 65], [179.5, 65]), 6);
    expect(east).toBeCloseTo(haversineMeters([179.5, 65], [180.5, 65]), 6);
    expect(east).toBeLessThan(50_000);
  });

  it("matches a known distance between Novorossiysk and Sochi", () => {
    expect(haversineMeters([37.7686, 44.7239], [39.7303, 43.5855]) / 1000).toBeCloseTo(201.3, 0);
  });
});

describe("formatRulerDistance", () => {
  it.each([
    [0, "0 м"],
    [12.4, "12 м"],
    [340, "340 м"],
    [999.4, "999 м"],
    [999.6, "1,00 км"],
    [1000, "1,00 км"],
    [2450, "2,45 км"],
    [2454.9, "2,45 км"],
    [87_125, "87,13 км"],
  ])("formats %s m as %s", (meters, expected) => {
    expect(formatRulerDistance(meters)).toBe(expected);
  });

  it("groups thousands of kilometres with a Russian separator", () => {
    expect(formatRulerDistance(1_234_567)).toMatch(/^1\s234,57 км$/u);
  });
});

describe("great circle path", () => {
  it("keeps the endpoints and splits long legs", () => {
    const from: LngLat = [30, 70];
    const to: LngLat = [60, 70];
    const path = greatCirclePath(from, to);
    expect(path[0]).toEqual(from);
    expect(path.at(-1)).toEqual(to);
    expect(path.length).toBeGreaterThan(10);
  });

  it("bows toward the pole at high latitude", () => {
    const [, lat] = interpolateGreatCircle([30, 70], [60, 70], 0.5);
    expect(lat).toBeGreaterThan(70);
  });

  it("places the midpoint halfway along the arc", () => {
    const from: LngLat = [30, 70];
    const to: LngLat = [60, 70];
    const middle = interpolateGreatCircle(from, to, 0.5);
    expect(haversineMeters(from, middle)).toBeCloseTo(haversineMeters(from, to) / 2, 3);
  });

  it("stays continuous across the antimeridian", () => {
    const path = greatCirclePath([175, 65], [185, 65]);
    path.slice(1).forEach(([lng], index) => {
      expect(Math.abs(lng - path[index][0])).toBeLessThan(5);
    });
  });
});

describe("rulerSegments", () => {
  it("adds a draft leg to the cursor and sums the legs", () => {
    const points: LngLat[] = [
      [37, 44],
      [37, 45],
    ];
    const segments = rulerSegments(points, [38, 45]);
    expect(segments.map((entry) => entry.draft)).toEqual([false, true]);
    expect(totalMeters(segments)).toBeCloseTo(
      haversineMeters([37, 44], [37, 45]) + haversineMeters([37, 45], [38, 45]),
      6,
    );
  });

  it("is empty for a single point without a cursor", () => {
    expect(rulerSegments([[37, 44]], null)).toEqual([]);
  });
});
