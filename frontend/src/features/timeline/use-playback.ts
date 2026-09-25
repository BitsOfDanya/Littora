"use client";

import { useCallback, useEffect } from "react";
import { stepIndex } from "./compare-model";
import { useCompareViewStore } from "./compare-view-store";
import { type CompareActions, type CompareData } from "./use-compare";

const PLAYBACK_STEP_MS = 1000;

export function usePlaybackController(data: CompareData, actions: CompareActions): void {
  const playing = useCompareViewStore((state) => state.playing);
  const setPlaying = useCompareViewStore((state) => state.setPlaying);
  const { scenes, pair } = data;

  useEffect(() => {
    if (!playing) return;
    const next = pair ? stepIndex(scenes, pair.bIndex, 1, { skip: pair.aIndex }) : null;
    const timer = window.setTimeout(() => {
      if (next === null) setPlaying(false);
      else actions.setSide("b", scenes[next].id);
    }, PLAYBACK_STEP_MS);
    return () => window.clearTimeout(timer);
  }, [playing, pair, scenes, actions, setPlaying]);

  useEffect(() => () => setPlaying(false), [setPlaying]);
}

export function useTogglePlayback(data: CompareData, actions: CompareActions): () => void {
  const { pair, scenes } = data;
  return useCallback(() => {
    const store = useCompareViewStore.getState();
    if (store.playing) {
      store.setPlaying(false);
      return;
    }
    if (!pair) return;
    const atEnd = stepIndex(scenes, pair.bIndex, 1, { skip: pair.aIndex }) === null;
    const first = stepIndex(scenes, pair.aIndex, 1);
    if (atEnd && first !== null && first !== pair.bIndex) actions.setSide("b", scenes[first].id);
    store.setPlaying(true);
  }, [pair, scenes, actions]);
}
