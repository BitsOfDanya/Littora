import { describe, expect, it } from "vitest";
import type { CandidateHistory, CandidatePass } from "@/data/timeline";
import type { SceneSummary, SceneUsability } from "@/domain/scene";
import {
  areaSeries,
  compassPoint,
  coverageSeries,
  deltaKindOf,
  displacementBetween,
  intervalOf,
  nearestUsablePair,
  nextDividerPosition,
  objectDynamics,
  resolvePair,
  sideTotals,
  stepIndex,
} from "./compare-model";

function scene(day: number, usability: SceneUsability, cloudCover = 0.1): SceneSummary {
  const date = `2026-09-${String(day).padStart(2, "0")}T16:05:00Z`;
  return {
    id: `S${day}`,
    aoiId: "test",
    platform: "S2B",
    processingLevel: "L2A",
    acquiredAt: date,
    mgrsTile: "16PDC",
    relativeOrbit: 97,
    footprint: [0, 0, 1, 1],
    cloudCover,
    validWaterFraction: 1 - cloudCover,
    sunGlintRisk: "low",
    sunZenithDeg: 30,
    usability,
  };
}

const SCENES = [
  scene(1, "usable"),
  scene(6, "partial", 0.5),
  scene(11, "unusable", 0.9),
  scene(16, "usable"),
  scene(21, "partial", 0.64),
  scene(26, "usable"),
];

function pass(
  sceneId: string,
  state: CandidatePass["state"],
  area = 0,
  coverage = 0,
): CandidatePass {
  const found = state === "found";
  return {
    sceneId,
    observedAt: "2026-09-01T00:00:00Z",
    state,
    geometry: null,
    centroid: found ? [-88.2, 15.8] : null,
    areaM2: found ? area : null,
    coverage: found ? { value: coverage, low: coverage * 0.6, high: coverage * 1.4 } : null,
  };
}

const HISTORY: CandidateHistory = {
  candidateId: "LT-1",
  passes: [
    pass("S1", "not-found"),
    pass("S6", "cloudy"),
    pass("S11", "no-data"),
    pass("S16", "found", 200_000, 0.1),
    pass("S21", "found", 300_000, 0.15),
    pass("S26", "found", 400_000, 0.2),
  ],
};

describe("compare pair", () => {
  it("falls back to the third-from-last and the last scene", () => {
    const pair = resolvePair(SCENES, null, null);
    expect(pair?.a.id).toBe("S16");
    expect(pair?.b.id).toBe("S26");
  });

  it("never resolves A and B to the same scene", () => {
    const pair = resolvePair(SCENES, "S26", "S26");
    expect(pair?.aIndex).toBe(4);
    expect(pair?.bIndex).toBe(5);
  });

  it("needs two scenes", () => {
    expect(resolvePair(SCENES.slice(0, 1), null, null)).toBeNull();
  });

  it("steps over the other side and optionally over unusable passes", () => {
    expect(stepIndex(SCENES, 3, 1, { skip: 4 })).toBe(5);
    expect(stepIndex(SCENES, 5, -1, { usableOnly: true })).toBe(3);
    expect(stepIndex(SCENES, 5, 1)).toBeNull();
  });

  it("finds the nearest usable pair keeping A before B", () => {
    const pair = resolvePair(SCENES, "S21", "S26");
    expect(pair && nearestUsablePair(SCENES, pair)).toEqual({
      beforeSceneId: "S16",
      afterSceneId: "S26",
    });
  });

  it("counts the passes strictly between A and B", () => {
    const pair = resolvePair(SCENES, "S1", "S26");
    expect(pair && intervalOf(SCENES, pair)).toEqual({
      days: 25,
      between: 4,
      usableBetween: 1,
      reversed: false,
    });
  });
});

describe("deltas", () => {
  it("classifies the object state across the pair", () => {
    const found = pass("x", "found", 1, 0.1);
    expect(deltaKindOf(found, found)).toBe("change");
    expect(deltaKindOf(pass("x", "not-found"), found)).toBe("new");
    expect(deltaKindOf(found, pass("x", "not-found"))).toBe("gone");
    expect(deltaKindOf(pass("x", "cloudy"), found)).toBe("hidden");
    expect(deltaKindOf(null, found)).toBe("hidden");
  });

  it("sums only the objects seen at a scene and counts the hidden ones", () => {
    const totals = sideTotals([HISTORY], SCENES[4]);
    expect(totals.found).toBe(1);
    expect(totals.areaM2).toBe(300_000);
    expect(totals.coverage?.value).toBeCloseTo(0.15);
    expect(sideTotals([HISTORY], SCENES[1]).hidden).toBe(1);
  });

  it("measures area change and persistence up to the later side", () => {
    const pair = resolvePair(SCENES, "S16", "S26");
    const dynamics = pair && objectDynamics(HISTORY, SCENES, pair);
    expect(dynamics?.areaRatio).toBeCloseTo(1);
    expect(dynamics?.persistence).toEqual({ found: 2, usable: 3 });
  });
});

describe("series never bridge cloudy passes", () => {
  it("marks cloudy and no-data passes as gaps", () => {
    const states = coverageSeries(HISTORY, SCENES).map((point) => point.state);
    expect(states).toEqual(["not-found", "cloudy", "no-data", "observed", "observed", "observed"]);
  });

  it("treats a partly cloudy scene as a gap in the area total", () => {
    const series = areaSeries([HISTORY], SCENES);
    expect(series[4].state).toBe("cloudy");
    expect(series[4].value).toBeUndefined();
    expect(series[5].value).toBeCloseTo(0.4);
  });
});

describe("geometry helpers", () => {
  it("names 16 compass points in Russian", () => {
    expect(compassPoint(0)).toBe("С");
    expect(compassPoint(248)).toBe("ЗЮЗ");
    expect(compassPoint(359)).toBe("С");
    expect(compassPoint(-90)).toBe("З");
  });

  it("returns distance and bearing between two points", () => {
    const moved = displacementBetween([-88.2, 15.8], [-88.2, 15.81]);
    expect(moved.distanceM).toBeCloseTo(1113, -1);
    expect(moved.bearingDeg).toBeCloseTo(0);
  });
});

describe("divider keys", () => {
  it("steps by 5 % and 20 % and stays within the frame", () => {
    expect(nextDividerPosition(0.5, "increase")).toBe(0.55);
    expect(nextDividerPosition(0.5, "decrease", true)).toBe(0.3);
    expect(nextDividerPosition(0.1, "decrease", true)).toBe(0);
    expect(nextDividerPosition(0.3, "end")).toBe(1);
    expect(nextDividerPosition(0.3, "start")).toBe(0);
  });
});
