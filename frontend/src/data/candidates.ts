"use client";

import { DEMO_CANDIDATES } from "@/demo/candidates";
import { DEMO_TRACK } from "@/demo/timeline";
import { useDemoSourced } from "./use-sourced";

export const useCandidates = () => useDemoSourced(DEMO_CANDIDATES);

export const useCandidateTrack = () => useDemoSourced(DEMO_TRACK);
