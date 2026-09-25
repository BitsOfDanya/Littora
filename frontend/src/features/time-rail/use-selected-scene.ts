"use client";

import { useMemo } from "react";
import { useScenes } from "@/data/scenes";
import type { SceneSummary } from "@/domain/scene";
import { useWorkspaceStore } from "@/state/workspace-store";

export type SelectedScene = {
  scenes: readonly SceneSummary[];
  scene: SceneSummary | null;
  index: number;
  isLatest: boolean;
  isDemo: boolean;
};

const NO_SCENES: readonly SceneSummary[] = [];

export function useSelectedScene(): SelectedScene {
  const sourced = useScenes();
  const sceneId = useWorkspaceStore((state) => state.sceneId);
  const scenes = sourced.origin === "none" ? NO_SCENES : sourced.data;
  const isDemo = sourced.origin === "demo";
  return useMemo(() => {
    const found = scenes.findIndex((scene) => scene.id === sceneId);
    const index = found === -1 ? scenes.length - 1 : found;
    return {
      scenes,
      scene: scenes[index] ?? null,
      index,
      isLatest: index === scenes.length - 1,
      isDemo,
    };
  }, [scenes, sceneId, isDemo]);
}
