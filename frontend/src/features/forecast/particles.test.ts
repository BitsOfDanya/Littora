import { describe, expect, it } from "vitest";
import {
  advanceBatch,
  PARTICLES,
  type ParticleField,
  particleCount,
  seedParticles,
  seededRng,
  staticStreaks,
  stepPosition,
  type ViewBox,
} from "./particles";

const COAST_LNG = -88.1;

const FIELD: ParticleField = {
  isWater: (lng) => lng < COAST_LNG,
  velocityAt: (lng) => (lng < COAST_LNG ? [0.2, 0.05] : null),
};

const VIEW: ViewBox = { west: -88.4, south: 15.7, east: -88.0, north: 16.0 };

describe("current particles", () => {
  it("scales the particle count with the map area and caps it at 400", () => {
    expect(particleCount(1_012, 688)).toBe(348);
    expect(particleCount(3_000, 2_000)).toBe(PARTICLES.max);
    expect(particleCount(200, 200)).toBe(PARTICLES.min);
  });

  it("stops a particle at the coast instead of stepping onto land", () => {
    expect(stepPosition(FIELD, [COAST_LNG - 0.0001, 15.8], 600)).toBeNull();
    const moved = stepPosition(FIELD, [-88.3, 15.8], 600);
    expect(moved?.[0]).toBeGreaterThan(-88.3);
  });

  it("keeps every trail vertex on water, inside the view and evenly timed", () => {
    const rng = seededRng(7);
    const states = seedParticles(FIELD, VIEW, rng, 120);
    expect(states.length).toBe(120);
    const batch = advanceBatch(FIELD, VIEW, states, rng, 400);
    expect(batch.trips.length).toBeGreaterThan(0);
    for (const trip of batch.trips) {
      expect(trip.path.length).toBe(trip.timestamps.length);
      trip.path.forEach(([lng, lat]) => {
        expect(FIELD.isWater(lng, lat)).toBe(true);
        expect(lng).toBeGreaterThanOrEqual(VIEW.west);
        expect(lat).toBeLessThanOrEqual(VIEW.north);
      });
      trip.timestamps.slice(1).forEach((time, index) => {
        expect(time - trip.timestamps[index]).toBeCloseTo(PARTICLES.vertexStepS, 6);
      });
      expect(trip.timestamps[0]).toBeGreaterThanOrEqual(
        -PARTICLES.trailSegments * PARTICLES.vertexStepS - 1e-9,
      );
      expect(trip.timestamps.at(-1)!).toBeLessThanOrEqual(batch.duration + 1e-9);
    }
  });

  it("carries at most six trail segments into the next batch", () => {
    const rng = seededRng(3);
    const batch = advanceBatch(FIELD, VIEW, seedParticles(FIELD, VIEW, rng, 40), rng, 400);
    for (const state of batch.next) {
      expect(state.trail.length).toBeLessThanOrEqual(PARTICLES.trailSegments + 1);
    }
  });

  it("draws static streaks for reduced motion", () => {
    const streaks = staticStreaks(FIELD, VIEW, seededRng(11), 50, 400);
    expect(streaks.length).toBeGreaterThan(0);
    for (const streak of streaks) {
      expect(streak.path.length).toBeLessThanOrEqual(PARTICLES.streakVertices);
    }
  });
});
