import type { CurrentField } from "@/data/forecast";
import type { LngLat } from "@/domain/geo";
import { offsetLngLat } from "@/lib/geo/local-metric";

export type ParticleField = Pick<CurrentField, "velocityAt" | "isWater">;

export type ViewBox = { west: number; south: number; east: number; north: number };

export type ParticleTrip = { path: [number, number][]; timestamps: number[] };

export type ParticleState = { position: LngLat; age: number; life: number; trail: LngLat[] };

export type ParticleBatch = { trips: ParticleTrip[]; duration: number; next: ParticleState[] };

export type Rng = () => number;

export const PARTICLES = {
  max: 400,
  min: 60,
  pixelsPerParticle: 2_000,
  trailSegments: 6,
  vertexStepS: 0.12,
  batchS: 6,
  lifeS: [2.4, 5.2] as const,
  pixelsPerSecond: 20,
  spawnAttempts: 16,
  streakVertices: 7,
} as const;

export function particleCount(widthPx: number, heightPx: number): number {
  const count = Math.round((widthPx * heightPx) / PARTICLES.pixelsPerParticle);
  return Math.min(PARTICLES.max, Math.max(PARTICLES.min, count));
}

export function timeScaleFor(metersPerPixel: number, typicalSpeedMs: number): number {
  return (PARTICLES.pixelsPerSecond * metersPerPixel) / Math.max(typicalSpeedMs, 0.01);
}

export function seededRng(seed: number): Rng {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function inside(view: ViewBox, [lng, lat]: LngLat): boolean {
  return lng >= view.west && lng <= view.east && lat >= view.south && lat <= view.north;
}

function randomLife(rng: Rng): number {
  const [low, high] = PARTICLES.lifeS;
  return low + (high - low) * rng();
}

export function spawnParticle(
  field: ParticleField,
  view: ViewBox,
  rng: Rng,
  age = 0,
): ParticleState | null {
  for (let attempt = 0; attempt < PARTICLES.spawnAttempts; attempt += 1) {
    const position: LngLat = [
      view.west + (view.east - view.west) * rng(),
      view.south + (view.north - view.south) * rng(),
    ];
    if (field.velocityAt(position[0], position[1])) {
      const life = randomLife(rng);
      return { position, age: Math.min(age, life * 0.9), life, trail: [position] };
    }
  }
  return null;
}

export function seedParticles(
  field: ParticleField,
  view: ViewBox,
  rng: Rng,
  count: number,
): ParticleState[] {
  const states: ParticleState[] = [];
  for (let index = 0; index < count; index += 1) {
    const state = spawnParticle(field, view, rng, rng() * PARTICLES.lifeS[1]);
    if (state) states.push(state);
  }
  return states;
}

export function stepPosition(
  field: ParticleField,
  position: LngLat,
  realSeconds: number,
): LngLat | null {
  const first = field.velocityAt(position[0], position[1]);
  if (!first) return null;
  const middle = offsetLngLat(position, [
    (first[0] * realSeconds) / 2,
    (first[1] * realSeconds) / 2,
  ]);
  const second = field.velocityAt(middle[0], middle[1]) ?? first;
  const next = offsetLngLat(position, [second[0] * realSeconds, second[1] * realSeconds]);
  return field.isWater(next[0], next[1]) ? next : null;
}

function tripFrom(trail: readonly LngLat[], lastTime: number): ParticleTrip {
  const path = trail.map(([lng, lat]) => [lng, lat] as [number, number]);
  const timestamps = trail.map(
    (_, index) => lastTime - (trail.length - 1 - index) * PARTICLES.vertexStepS,
  );
  return { path, timestamps };
}

export function advanceBatch(
  field: ParticleField,
  view: ViewBox,
  states: readonly ParticleState[],
  rng: Rng,
  timeScale: number,
): ParticleBatch {
  const steps = Math.round(PARTICLES.batchS / PARTICLES.vertexStepS);
  const realStep = PARTICLES.vertexStepS * timeScale;
  const trips: ParticleTrip[] = [];
  const next: ParticleState[] = [];

  for (const initial of states) {
    let state: ParticleState = initial;
    let trip: LngLat[] = [...initial.trail];
    let tripEnd = 0;
    const closeTrip = () => {
      if (trip.length >= 2) trips.push(tripFrom(trip, tripEnd));
    };
    for (let step = 1; step <= steps; step += 1) {
      const time = step * PARTICLES.vertexStepS;
      const moved = state.age < state.life ? stepPosition(field, state.position, realStep) : null;
      if (moved && inside(view, moved)) {
        state = { ...state, position: moved, age: state.age + PARTICLES.vertexStepS };
        trip.push(moved);
        tripEnd = time;
        continue;
      }
      closeTrip();
      const reborn = spawnParticle(field, view, rng);
      if (!reborn) {
        trip = [];
        break;
      }
      state = reborn;
      trip = [reborn.position];
      tripEnd = time;
    }
    closeTrip();
    if (trip.length) {
      next.push({ ...state, trail: trip.slice(-(PARTICLES.trailSegments + 1)) });
    }
  }

  return { trips, duration: steps * PARTICLES.vertexStepS, next };
}

export function staticStreaks(
  field: ParticleField,
  view: ViewBox,
  rng: Rng,
  count: number,
  timeScale: number,
): ParticleTrip[] {
  const realStep = PARTICLES.vertexStepS * timeScale * 1.5;
  const streaks: ParticleTrip[] = [];
  for (let index = 0; index < count; index += 1) {
    const seed = spawnParticle(field, view, rng);
    if (!seed) continue;
    const path: [number, number][] = [[seed.position[0], seed.position[1]]];
    let position: LngLat | null = seed.position;
    for (let step = 1; step < PARTICLES.streakVertices && position; step += 1) {
      position = stepPosition(field, position, realStep);
      if (position) path.push([position[0], position[1]]);
    }
    if (path.length >= 2) streaks.push({ path, timestamps: path.map((_, step) => step) });
  }
  return streaks;
}
