"use client";

import { useCallback, useMemo } from "react";
import type { SceneSummary } from "@/domain/scene";
import { useHotkey } from "@/features/shell/hotkeys";
import { useShellUiStore } from "@/state/shell-ui-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { nearestIndex } from "./rail-model";

export function isUsableScene(scene: SceneSummary): boolean {
  return scene.usability === "usable";
}

export function useSceneStepping(
  scenes: readonly SceneSummary[],
  { hotkeys = true }: { hotkeys?: boolean } = {},
) {
  const sceneId = useWorkspaceStore((state) => state.sceneId);
  const selectScene = useWorkspaceStore((state) => state.selectScene);

  const currentIndex = useMemo(() => {
    const index = scenes.findIndex((scene) => scene.id === sceneId);
    return index === -1 ? scenes.length - 1 : index;
  }, [scenes, sceneId]);

  const current = scenes[currentIndex] ?? null;

  const step = useCallback(
    (delta: number, usableOnly = false) => {
      for (let index = currentIndex + delta; index >= 0 && index < scenes.length; index += delta) {
        if (!usableOnly || isUsableScene(scenes[index])) {
          selectScene(scenes[index].id);
          return true;
        }
      }
      return false;
    },
    [currentIndex, scenes, selectScene],
  );

  const nearestUsable = useMemo(
    () =>
      current && !isUsableScene(current) ? nearestIndex(scenes, currentIndex, isUsableScene) : -1,
    [current, currentIndex, scenes],
  );

  const jumpToNearestUsable = useCallback(() => {
    if (nearestUsable !== -1) selectScene(scenes[nearestUsable].id);
  }, [nearestUsable, scenes, selectScene]);

  const canStepToUsable = useMemo(
    () => scenes.some((scene, index) => index > currentIndex && isUsableScene(scene)),
    [scenes, currentIndex],
  );

  const modalOpen = useShellUiStore((state) => state.shortcutSheetOpen);
  const enabled = hotkeys && !modalOpen && scenes.length > 0;
  useHotkey("BracketLeft", () => step(-1), { enabled });
  useHotkey("BracketRight", () => step(1), { enabled });
  useHotkey("BracketLeft", () => step(-1, true), { enabled, shift: true });
  useHotkey("BracketRight", () => step(1, true), { enabled, shift: true });

  return {
    current,
    currentIndex,
    canStepBack: currentIndex > 0,
    canStepForward: currentIndex < scenes.length - 1,
    canStepToUsable,
    nearestUsable: nearestUsable === -1 ? null : scenes[nearestUsable],
    jumpToNearestUsable,
    step,
    select: selectScene,
  };
}
