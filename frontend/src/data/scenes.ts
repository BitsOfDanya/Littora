"use client";

import { DEMO_PLANNED_PASSES, DEMO_SCENES } from "@/demo/scenes";
import { useDemoSourced } from "./use-sourced";

export type { PlannedPass } from "@/demo/scenes";

export const useScenes = () => useDemoSourced(DEMO_SCENES);

export const usePlannedPasses = () => useDemoSourced(DEMO_PLANNED_PASSES);
