import type { CandidateHistory, CandidatePass } from "@/data/timeline";
import type { DebrisCandidate } from "@/domain/detection";
import type { LngLat } from "@/domain/geo";
import type { Estimate } from "@/domain/measurement";
import type { SceneSummary } from "@/domain/scene";
import type { SeriesPoint } from "@/features/inspector/parts/observation-series";
import { toLocalMeters } from "@/lib/geo/local-metric";

export const DAY_MS = 86_400_000;
export const DIVIDER_STEP = 0.05;
export const DIVIDER_STEP_LARGE = 0.2;
export const DEFAULT_A_FROM_END = 3;
export const MOSAIC_YEARS = { a: 2024, b: 2025 } as const;

export type CompareSide = "a" | "b";

export type ComparePair = {
  a: SceneSummary;
  b: SceneSummary;
  aIndex: number;
  bIndex: number;
};

export function isUsable(scene: SceneSummary): boolean {
  return scene.usability === "usable";
}

export function usableCount(scenes: readonly SceneSummary[]): number {
  return scenes.filter(isUsable).length;
}

function indexOfScene(scenes: readonly SceneSummary[], id: string | null): number {
  return id ? scenes.findIndex((scene) => scene.id === id) : -1;
}

export function defaultPairIds(
  scenes: readonly SceneSummary[],
): { beforeSceneId: string; afterSceneId: string } | null {
  if (scenes.length < 2) return null;
  const usable = scenes.filter(isUsable);
  if (usable.length >= 2) {
    return {
      beforeSceneId: usable[usable.length - 2].id,
      afterSceneId: usable[usable.length - 1].id,
    };
  }
  const after = scenes[scenes.length - 1];
  const before = scenes[Math.max(0, scenes.length - DEFAULT_A_FROM_END)];
  return { beforeSceneId: before.id, afterSceneId: after.id };
}

export function resolvePair(
  scenes: readonly SceneSummary[],
  beforeId: string | null,
  afterId: string | null,
): ComparePair | null {
  if (scenes.length < 2) return null;
  const fallback = defaultPairIds(scenes);
  let bIndex = indexOfScene(scenes, afterId);
  if (bIndex === -1) bIndex = indexOfScene(scenes, fallback?.afterSceneId ?? null);
  let aIndex = indexOfScene(scenes, beforeId);
  if (aIndex === -1) aIndex = indexOfScene(scenes, fallback?.beforeSceneId ?? null);
  if (aIndex === bIndex) aIndex = bIndex > 0 ? bIndex - 1 : bIndex + 1;
  return { a: scenes[aIndex], b: scenes[bIndex], aIndex, bIndex };
}

export function stepIndex(
  scenes: readonly SceneSummary[],
  from: number,
  delta: 1 | -1,
  { usableOnly = false, skip = -1 }: { usableOnly?: boolean; skip?: number } = {},
): number | null {
  for (let index = from + delta; index >= 0 && index < scenes.length; index += delta) {
    if (index === skip) continue;
    if (usableOnly && !isUsable(scenes[index])) continue;
    return index;
  }
  return null;
}

function nearestUsable(
  scenes: readonly SceneSummary[],
  target: number,
  accept: (index: number) => boolean,
): number | null {
  let best: number | null = null;
  scenes.forEach((scene, index) => {
    if (!isUsable(scene) || !accept(index)) return;
    if (best === null || Math.abs(index - target) < Math.abs(best - target)) best = index;
  });
  return best;
}

export function nearestUsablePair(
  scenes: readonly SceneSummary[],
  pair: ComparePair,
): { beforeSceneId: string; afterSceneId: string } | null {
  if (usableCount(scenes) < 2) return null;
  const bIndex = nearestUsable(scenes, pair.bIndex, () => true);
  if (bIndex === null) return null;
  const forward = pair.aIndex < pair.bIndex;
  const aIndex =
    nearestUsable(scenes, pair.aIndex, (index) => (forward ? index < bIndex : index > bIndex)) ??
    nearestUsable(scenes, pair.aIndex, (index) => index !== bIndex);
  if (aIndex === null) return null;
  return { beforeSceneId: scenes[aIndex].id, afterSceneId: scenes[bIndex].id };
}

export function pairIsComplete(pair: ComparePair): boolean {
  return isUsable(pair.a) && isUsable(pair.b);
}

export type CompareInterval = {
  days: number;
  between: number;
  usableBetween: number;
  reversed: boolean;
};

export function intervalOf(scenes: readonly SceneSummary[], pair: ComparePair): CompareInterval {
  const low = Math.min(pair.aIndex, pair.bIndex);
  const high = Math.max(pair.aIndex, pair.bIndex);
  const inside = scenes.slice(low + 1, high);
  return {
    days: Math.round(
      Math.abs(Date.parse(pair.b.acquiredAt) - Date.parse(pair.a.acquiredAt)) / DAY_MS,
    ),
    between: inside.length,
    usableBetween: inside.filter(isUsable).length,
    reversed: pair.aIndex > pair.bIndex,
  };
}

export function passAt(
  history: CandidateHistory | undefined,
  sceneId: string,
): CandidatePass | undefined {
  return history?.passes.find((pass) => pass.sceneId === sceneId);
}

export type SideTotals = {
  found: number;
  hidden: number;
  areaM2: number;
  coverage: Estimate | null;
  validWater: number;
};

function mean(values: readonly number[]): number {
  return values.reduce((total, value) => total + value, 0) / values.length;
}

export function sideTotals(
  histories: readonly CandidateHistory[],
  scene: SceneSummary,
): SideTotals {
  const passes = histories.flatMap((history) => {
    const pass = passAt(history, scene.id);
    return pass ? [pass] : [];
  });
  const found = passes.filter((pass) => pass.state === "found");
  const coverages = found.flatMap((pass) => (pass.coverage ? [pass.coverage] : []));
  return {
    found: found.length,
    hidden: passes.filter((pass) => pass.state === "cloudy" || pass.state === "no-data").length,
    areaM2: found.reduce((total, pass) => total + (pass.areaM2 ?? 0), 0),
    coverage: coverages.length
      ? {
          value: mean(coverages.map((entry) => entry.value)),
          low: mean(coverages.map((entry) => entry.low)),
          high: mean(coverages.map((entry) => entry.high)),
        }
      : null,
    validWater: scene.validWaterFraction,
  };
}

export type DeltaKind = "change" | "new" | "gone" | "hidden" | "absent";

export type ObjectRow = {
  candidate: DebrisCandidate;
  a: CandidatePass | null;
  b: CandidatePass | null;
  kind: DeltaKind;
  deltaPp: number | null;
};

function isHidden(pass: CandidatePass | null): boolean {
  return !pass || pass.state === "cloudy" || pass.state === "no-data";
}

export function deltaKindOf(a: CandidatePass | null, b: CandidatePass | null): DeltaKind {
  if (isHidden(a) || isHidden(b)) return "hidden";
  const aFound = a?.state === "found";
  const bFound = b?.state === "found";
  if (aFound && bFound) return "change";
  if (bFound) return "new";
  if (aFound) return "gone";
  return "absent";
}

export function objectRows(
  candidates: readonly DebrisCandidate[],
  histories: readonly CandidateHistory[],
  pair: ComparePair,
): ObjectRow[] {
  return candidates.map((candidate) => {
    const history = histories.find((entry) => entry.candidateId === candidate.id);
    const a = passAt(history, pair.a.id) ?? null;
    const b = passAt(history, pair.b.id) ?? null;
    const kind = deltaKindOf(a, b);
    const deltaPp =
      kind === "change" && a?.coverage && b?.coverage
        ? (b.coverage.value - a.coverage.value) * 100
        : null;
    return { candidate, a, b, kind, deltaPp };
  });
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

export function compassPoint(bearingDeg: number): string {
  const normalized = ((bearingDeg % 360) + 360) % 360;
  return COMPASS_16[Math.round(normalized / 22.5) % 16];
}

export type Displacement = { distanceM: number; bearingDeg: number };

export function displacementBetween(from: LngLat, to: LngLat): Displacement {
  const [east, north] = toLocalMeters(from, to);
  const bearingDeg = ((Math.atan2(east, north) * 180) / Math.PI + 360) % 360;
  return { distanceM: Math.hypot(east, north), bearingDeg };
}

export type ObjectDynamics = {
  a: CandidatePass | null;
  b: CandidatePass | null;
  areaRatio: number | null;
  displacement: Displacement | null;
  persistence: { found: number; usable: number };
};

export function objectDynamics(
  history: CandidateHistory | undefined,
  scenes: readonly SceneSummary[],
  pair: ComparePair,
): ObjectDynamics {
  const a = passAt(history, pair.a.id) ?? null;
  const b = passAt(history, pair.b.id) ?? null;
  const bothFound = a?.state === "found" && b?.state === "found";
  const until = Math.max(pair.aIndex, pair.bIndex);
  const usableScenes = scenes.slice(0, until + 1).filter(isUsable);
  const found = usableScenes.filter((scene) => passAt(history, scene.id)?.state === "found");
  return {
    a,
    b,
    areaRatio: bothFound && a.areaM2 && b.areaM2 ? b.areaM2 / a.areaM2 - 1 : null,
    displacement:
      bothFound && a.centroid && b.centroid ? displacementBetween(a.centroid, b.centroid) : null,
    persistence: { found: found.length, usable: usableScenes.length },
  };
}

export function coverageSeries(
  history: CandidateHistory | undefined,
  scenes: readonly SceneSummary[],
): SeriesPoint[] {
  return scenes.map((scene) => {
    const pass = passAt(history, scene.id);
    const base = { id: scene.id, time: scene.acquiredAt, cloudCover: scene.cloudCover };
    if (!pass || pass.state === "no-data") return { ...base, state: "no-data" };
    if (pass.state === "cloudy") return { ...base, state: "cloudy" };
    if (pass.state === "not-found") return { ...base, state: "not-found", value: 0 };
    return {
      ...base,
      state: "observed",
      value: pass.coverage?.value,
      low: pass.coverage?.low,
      high: pass.coverage?.high,
    };
  });
}

export function areaSeries(
  histories: readonly CandidateHistory[],
  scenes: readonly SceneSummary[],
): SeriesPoint[] {
  return scenes.map((scene) => {
    const base = { id: scene.id, time: scene.acquiredAt, cloudCover: scene.cloudCover };
    if (scene.usability === "unusable") return { ...base, state: "no-data" };
    if (scene.usability === "partial") return { ...base, state: "cloudy" };
    return { ...base, state: "observed", value: sideTotals(histories, scene).areaM2 / 1_000_000 };
  });
}

export type DividerAction = "decrease" | "increase" | "start" | "end";

export function nextDividerPosition(
  position: number,
  action: DividerAction,
  large = false,
): number {
  const step = large ? DIVIDER_STEP_LARGE : DIVIDER_STEP;
  const next =
    action === "start"
      ? 0
      : action === "end"
        ? 1
        : position + (action === "increase" ? step : -step);
  return Math.round(Math.min(1, Math.max(0, next)) * 1000) / 1000;
}

export type TimeWindow = { start: number; end: number };

export function railWindow(scenes: readonly SceneSummary[], now: number, padDays = 3): TimeWindow {
  const times = scenes.map((scene) => Date.parse(scene.acquiredAt));
  const first = times.length ? Math.min(...times) : now - 30 * DAY_MS;
  const last = times.length ? Math.max(...times, now) : now;
  return { start: first - padDays * DAY_MS, end: last + padDays * DAY_MS };
}

export function ratioIn(window: TimeWindow, time: number): number {
  return (time - window.start) / (window.end - window.start);
}

export function dayMonth(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
}
