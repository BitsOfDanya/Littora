import type { PlannedPass, SurveyPlan, SurveyPlanTarget, SurveyScoreWeights } from "@/data/survey";
import type { LngLat } from "@/domain/geo";
import type { SurveyScoreComponent } from "@/domain/survey";
import { offsetLngLat, toLocalMeters } from "@/lib/geo/local-metric";

export const KNOT_KMH = 1.852;
export const DAY_MS = 86_400_000;
const EARTH_RADIUS_KM = 6371.0088;

export const SCORE_COMPONENTS: readonly SurveyScoreComponent[] = [
  "confidence",
  "coverage",
  "persistence",
  "drift_risk",
  "uncertainty",
  "accessibility",
];

export function scoreOf(
  components: Readonly<Partial<Record<SurveyScoreComponent, number>>>,
  weights: SurveyScoreWeights,
): number {
  const total = SCORE_COMPONENTS.reduce(
    (sum, key) => sum + (components[key] ?? 0) * weights[key],
    0,
  );
  return Math.round(total * 100) / 100;
}

export type RankedTarget = { target: SurveyPlanTarget; rank: number; score: number };

export function rankTargets(
  targets: readonly SurveyPlanTarget[],
  weights: SurveyScoreWeights,
  excluded: ReadonlySet<string> = new Set(),
): RankedTarget[] {
  return targets
    .filter((target) => !excluded.has(target.id))
    .map((target) => ({ target, score: scoreOf(target.components, weights) }))
    .sort((a, b) => b.score - a.score || a.target.id.localeCompare(b.target.id))
    .map((entry, index) => ({ ...entry, rank: index + 1 }));
}

export function isStrictlyDescending(values: readonly number[]): boolean {
  return values.every((value, index) => index === 0 || value < values[index - 1]);
}

export function departureIso(plan: SurveyPlan, date: string): string {
  return `${date}T${plan.departure.timeUtc}:00Z`;
}

export function windowDates(window: SurveyPlan["window"]): string[] {
  const dates: string[] = [];
  const end = Date.parse(`${window.to}T00:00:00Z`);
  for (let time = Date.parse(`${window.from}T00:00:00Z`); time <= end; time += DAY_MS)
    dates.push(new Date(time).toISOString().slice(0, 10));
  return dates;
}

export function stepDate(dates: readonly string[], current: string, delta: number): string {
  const index = dates.indexOf(current);
  if (index === -1) return dates[0] ?? current;
  return dates[Math.min(Math.max(index + delta, 0), dates.length - 1)];
}

export function elapsedDays(fromIso: string, toIso: string): number {
  return Math.max(0, (Date.parse(toIso) - Date.parse(fromIso)) / DAY_MS);
}

export function destination(origin: LngLat, bearingDeg: number, distanceKm: number): LngLat {
  const radians = (bearingDeg * Math.PI) / 180;
  const meters = distanceKm * 1000;
  return offsetLngLat(origin, [Math.sin(radians) * meters, Math.cos(radians) * meters]);
}

export type DriftState = { position: LngLat; shiftKm: number; radiusKm: number; days: number };

export function driftAt(target: SurveyPlanTarget, atIso: string): DriftState {
  const days = elapsedDays(target.observedAt, atIso);
  const shiftKm = target.drift.kmPerDay * days;
  return {
    position: destination(target.observedPosition, target.drift.bearingDeg, shiftKm),
    shiftKm,
    radiusKm: target.searchRadius.baseKm + target.searchRadius.kmPerDay * days,
    days,
  };
}

export function distanceKm(a: LngLat, b: LngLat): number {
  const toRad = (value: number) => (value * Math.PI) / 180;
  const dLat = toRad(b[1] - a[1]);
  const dLng = toRad(b[0] - a[0]);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a[1])) * Math.cos(toRad(b[1])) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function bearingDeg(from: LngLat, to: LngLat): number {
  const [east, north] = toLocalMeters(from, to);
  return ((Math.atan2(east, north) * 180) / Math.PI + 360) % 360;
}

export type RouteStopState = { targetId: string; visit: number; cumKm: number; vertex: number };

export type RouteState = { path: LngLat[]; stops: RouteStopState[]; totalKm: number };

export function buildRoute(plan: SurveyPlan, positions: ReadonlyMap<string, LngLat>): RouteState {
  const path: LngLat[] = [plan.port.berth];
  const stops: RouteStopState[] = [];
  let cumKm = 0;
  for (const stop of plan.route) {
    const position = stop.kind === "via" ? stop.position : positions.get(stop.targetId);
    if (!position) continue;
    cumKm += distanceKm(path[path.length - 1], position);
    path.push(position);
    if (stop.kind === "target")
      stops.push({
        targetId: stop.targetId,
        visit: stops.length + 1,
        cumKm,
        vertex: path.length - 1,
      });
  }
  return { path, stops, totalKm: cumKm };
}

export function transitMinutes(km: number, speedKn: number): number {
  return (km / (speedKn * KNOT_KMH)) * 60;
}

export function etaIso(
  departure: string,
  stop: RouteStopState,
  speedKn: number,
  dwellMin: number,
): string {
  const minutes = transitMinutes(stop.cumKm, speedKn) + (stop.visit - 1) * dwellMin;
  return new Date(Date.parse(departure) + minutes * 60_000).toISOString();
}

export function passCovers(pass: PlannedPass, position: LngLat): boolean {
  return position[0] >= pass.swath.westLng && position[0] <= pass.swath.eastLng;
}

export type PassRelation = { pass: PlannedPass; beforeDeparture: boolean };

export function nextPassFor(
  passes: readonly PlannedPass[],
  position: LngLat,
  nowIso: string,
  departure: string,
): PassRelation | null {
  const pass = [...passes]
    .filter(
      (entry) => passCovers(entry, position) && Date.parse(entry.acquiredAt) > Date.parse(nowIso),
    )
    .sort((a, b) => Date.parse(a.acquiredAt) - Date.parse(b.acquiredAt))[0];
  if (!pass) return null;
  return { pass, beforeDeparture: Date.parse(pass.acquiredAt) < Date.parse(departure) };
}

const COMPASS_16 = [
  "С",
  "ССВ",
  "СВ",
  "ВСВ",
  "В",
  "ВЮВ",
  "ЮВ",
  "ЮЮВ",
  "Ю",
  "ЮЮЗ",
  "ЮЗ",
  "ЗЮЗ",
  "З",
  "ЗСЗ",
  "СЗ",
  "ССЗ",
] as const;

export function compassPoint(bearing: number): string {
  const normalized = ((bearing % 360) + 360) % 360;
  return COMPASS_16[Math.round(normalized / 22.5) % 16];
}

export function circlePath(center: LngLat, radiusKm: number, steps = 72): LngLat[] {
  return Array.from({ length: steps + 1 }, (_, index) =>
    destination(center, (index / steps) * 360, radiusKm),
  );
}

export function nearestPointOnRing(point: LngLat, ring: readonly LngLat[]): LngLat {
  const origin = point;
  let best: { distance: number; at: [number, number] } | null = null;
  for (let index = 1; index < ring.length; index += 1) {
    const [ax, ay] = toLocalMeters(origin, ring[index - 1]);
    const [bx, by] = toLocalMeters(origin, ring[index]);
    const dx = bx - ax;
    const dy = by - ay;
    const lengthSq = dx * dx + dy * dy;
    const t = lengthSq === 0 ? 0 : Math.min(1, Math.max(0, -(ax * dx + ay * dy) / lengthSq));
    const x = ax + dx * t;
    const y = ay + dy * t;
    const distance = Math.hypot(x, y);
    if (!best || distance < best.distance) best = { distance, at: [x, y] };
  }
  return best ? offsetLngLat(origin, best.at) : point;
}

export function bboxOf(points: readonly LngLat[]): [number, number, number, number] | null {
  if (!points.length) return null;
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  for (const [lng, lat] of points) {
    west = Math.min(west, lng);
    east = Math.max(east, lng);
    south = Math.min(south, lat);
    north = Math.max(north, lat);
  }
  return [west, south, east, north];
}
