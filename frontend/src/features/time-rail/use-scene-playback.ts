"use client";

import { useEffect } from "react";
import { create } from "zustand";
import { isTypingTarget, useHotkey } from "@/features/shell/hotkeys";
import { useShellUiStore } from "@/state/shell-ui-store";

export type PlaybackSpeed = 1 | 2 | 4;

const SPEEDS: readonly PlaybackSpeed[] = [1, 2, 4];
const BASE_STEP_MS = 1600;

type PlaybackStore = {
  playing: boolean;
  speed: PlaybackSpeed;
  setPlaying: (playing: boolean) => void;
  cycleSpeed: () => void;
};

export const usePlaybackStore = create<PlaybackStore>()((set) => ({
  playing: false,
  speed: 1,
  setPlaying: (playing) => set({ playing }),
  cycleSpeed: () =>
    set((state) => ({ speed: SPEEDS[(SPEEDS.indexOf(state.speed) + 1) % SPEEDS.length] })),
}));

function isActivatable(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.closest("button, a, [role='radio'], [role='tab'], summary") !== null ||
      isTypingTarget(target))
  );
}

type PlaybackControls = {
  enabled: boolean;
  atEnd: boolean;
  onStep: () => boolean;
  onRestart: () => void;
};

export function useScenePlayback({ enabled, atEnd, onStep, onRestart }: PlaybackControls) {
  const playing = usePlaybackStore((state) => state.playing);
  const speed = usePlaybackStore((state) => state.speed);
  const setPlaying = usePlaybackStore((state) => state.setPlaying);
  const cycleSpeed = usePlaybackStore((state) => state.cycleSpeed);
  const modalOpen = useShellUiStore((state) => state.shortcutSheetOpen);

  const toggle = () => {
    if (!enabled) return;
    if (playing) {
      setPlaying(false);
      return;
    }
    if (atEnd) onRestart();
    setPlaying(true);
  };

  useEffect(() => {
    if (!playing || !enabled) return;
    const timer = window.setInterval(() => {
      if (!onStep()) setPlaying(false);
    }, BASE_STEP_MS / speed);
    return () => window.clearInterval(timer);
  }, [playing, enabled, speed, onStep, setPlaying]);

  useEffect(() => {
    if (!enabled && playing) setPlaying(false);
  }, [enabled, playing, setPlaying]);

  useEffect(() => () => setPlaying(false), [setPlaying]);

  useHotkey(
    "Space",
    (event) => {
      if (isActivatable(event.target)) return;
      event.preventDefault();
      toggle();
    },
    { enabled: enabled && !modalOpen, preventDefault: false },
  );

  return { playing, speed, toggle, cycleSpeed };
}
