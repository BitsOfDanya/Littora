"use client";

import { useCallback, useMemo } from "react";
import { useCandidates } from "@/data/candidates";
import { useScenes } from "@/data/scenes";
import {
  type CandidateHistory,
  type LiveTimeline,
  useCandidateHistories,
  useLiveTimeline,
} from "@/data/timeline";
import type { DebrisCandidate } from "@/domain/detection";
import type { SceneSummary } from "@/domain/scene";
import { useWorkspaceStore } from "@/state/workspace-store";
import {
  type ComparePair,
  type CompareSide,
  nearestUsablePair,
  resolvePair,
  stepIndex,
  usableCount,
} from "./compare-model";
import type { LivePasses } from "./live-model";

const NO_SCENES: readonly SceneSummary[] = [];
const NO_HISTORIES: readonly CandidateHistory[] = [];
const NO_CANDIDATES: readonly DebrisCandidate[] = [];
const NO_PASSES: LivePasses = new Map();

export type CompareData = {
  scenes: readonly SceneSummary[];
  histories: readonly CandidateHistory[];
  candidates: readonly DebrisCandidate[];
  pair: ComparePair | null;
  isDemo: boolean;
  hasCatalog: boolean;
  usable: number;
  enoughUsable: boolean;
  live: LiveTimeline;
  passes: LivePasses;
};

export function useCompareData(): CompareData {
  const scenesSourced = useScenes();
  const historiesSourced = useCandidateHistories();
  const candidatesSourced = useCandidates();
  const live = useLiveTimeline();
  const beforeId = useWorkspaceStore((state) => state.compare.beforeSceneId);
  const afterId = useWorkspaceStore((state) => state.compare.afterSceneId);
  const scenes = scenesSourced.origin === "none" ? NO_SCENES : scenesSourced.data;
  const histories = historiesSourced.origin === "none" ? NO_HISTORIES : historiesSourced.data;
  const candidates = candidatesSourced.origin === "none" ? NO_CANDIDATES : candidatesSourced.data;
  const pair = useMemo(() => resolvePair(scenes, beforeId, afterId), [scenes, beforeId, afterId]);
  const usable = usableCount(scenes);
  return {
    scenes,
    histories,
    candidates,
    pair,
    isDemo: scenesSourced.origin === "demo",
    hasCatalog: scenesSourced.origin !== "none",
    usable,
    enoughUsable: usable >= 2,
    live,
    passes: live.status === "ready" ? live.bySceneId : NO_PASSES,
  };
}

export type CompareActions = {
  setSide: (side: CompareSide, sceneId: string) => void;
  step: (side: CompareSide, delta: 1 | -1, usableOnly?: boolean) => void;
  canStep: (side: CompareSide, delta: 1 | -1) => boolean;
  swap: () => void;
  toNearestUsablePair: () => void;
};

export function useCompareActions(
  scenes: readonly SceneSummary[],
  pair: ComparePair | null,
): CompareActions {
  const updateCompare = useWorkspaceStore((state) => state.updateCompare);

  const setSide = useCallback(
    (side: CompareSide, sceneId: string) => {
      if (!pair) return;
      const other = side === "a" ? pair.b.id : pair.a.id;
      if (sceneId === other) return;
      updateCompare(
        side === "a"
          ? { beforeSceneId: sceneId, afterSceneId: pair.b.id }
          : { beforeSceneId: pair.a.id, afterSceneId: sceneId },
      );
    },
    [pair, updateCompare],
  );

  const target = useCallback(
    (side: CompareSide, delta: 1 | -1, usableOnly = false) => {
      if (!pair) return null;
      const from = side === "a" ? pair.aIndex : pair.bIndex;
      const skip = side === "a" ? pair.bIndex : pair.aIndex;
      return stepIndex(scenes, from, delta, { usableOnly, skip });
    },
    [pair, scenes],
  );

  const step = useCallback(
    (side: CompareSide, delta: 1 | -1, usableOnly = false) => {
      const index = target(side, delta, usableOnly);
      if (index !== null) setSide(side, scenes[index].id);
    },
    [scenes, setSide, target],
  );

  const canStep = useCallback(
    (side: CompareSide, delta: 1 | -1) => target(side, delta) !== null,
    [target],
  );

  const swap = useCallback(() => {
    if (pair) updateCompare({ beforeSceneId: pair.b.id, afterSceneId: pair.a.id });
  }, [pair, updateCompare]);

  const toNearestUsablePair = useCallback(() => {
    const next = pair ? nearestUsablePair(scenes, pair) : null;
    if (next) updateCompare(next);
  }, [pair, scenes, updateCompare]);

  return { setSide, step, canStep, swap, toNearestUsablePair };
}
