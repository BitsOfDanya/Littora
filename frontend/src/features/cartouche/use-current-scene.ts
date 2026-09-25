"use client";

import { useScenes } from "@/data/scenes";
import type { SceneSummary } from "@/domain/scene";
import { useWorkspaceStore } from "@/state/workspace-store";

export type CurrentScene = { scene: SceneSummary; isDemo: boolean } | null;

export function useSceneList(): { scenes: readonly SceneSummary[]; isDemo: boolean } {
  const sourced = useScenes();
  return sourced.origin === "none"
    ? { scenes: [], isDemo: false }
    : { scenes: sourced.data, isDemo: sourced.origin === "demo" };
}

export function useCurrentScene(): CurrentScene {
  const { scenes, isDemo } = useSceneList();
  const sceneId = useWorkspaceStore((state) => state.sceneId);
  const scene = scenes.find((entry) => entry.id === sceneId) ?? scenes.at(-1);
  return scene ? { scene, isDemo } : null;
}
