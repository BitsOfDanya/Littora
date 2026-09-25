"use client";

import { DEMO_SCENE_CONDITIONS } from "@/demo/masks";
import type { Sourced } from "@/domain/data-origin";
import type { SceneConditions } from "@/demo/masks";
import { useDemoSourced } from "./use-sourced";

export type { NoDataArea, NoDataKind, SceneConditions, UncertaintyArea } from "@/demo/masks";

const EMPTY_CONDITIONS: Readonly<Record<string, SceneConditions>> = {};

export function useSceneConditions(sceneId: string | null): Sourced<SceneConditions | null> {
  const sourced = useDemoSourced(DEMO_SCENE_CONDITIONS);
  if (sourced.origin === "none") return sourced;
  const table = sourced.data ?? EMPTY_CONDITIONS;
  return { origin: sourced.origin, data: sceneId ? (table[sceneId] ?? null) : null };
}
