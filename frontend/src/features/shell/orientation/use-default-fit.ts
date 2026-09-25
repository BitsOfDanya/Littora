"use client";

import { useEffect } from "react";
import { findAoi } from "@/config/aois";
import { useCandidates } from "@/data/candidates";
import { fitDefaultOnce, isDefaultFitDone } from "@/features/map/camera";
import { useMapViewStore } from "@/features/map/state/map-view-store";
import { useMainMap } from "@/features/map/use-main-map";
import { useViewportPaddingStore } from "@/features/map/use-viewport-padding";
import { useWorkspaceStore } from "@/state/workspace-store";

const LAYOUT_SETTLE_MS = 120;

export function useDefaultFit(): void {
  const map = useMainMap();
  const isReady = useMapViewStore((state) => state.isReady);
  const padding = useViewportPaddingStore((state) => state.target);
  const aoi = findAoi(useWorkspaceStore((state) => state.aoiId));
  const candidates = useCandidates();
  const candidateList = candidates.origin === "none" ? null : candidates.data;

  useEffect(() => {
    if (isDefaultFitDone() || !map || !isReady || !padding || !aoi) return;
    const timer = window.setTimeout(() => {
      fitDefaultOnce(map, { aoi, candidates: candidateList }, { durationMs: 0, padding });
    }, LAYOUT_SETTLE_MS);
    return () => window.clearTimeout(timer);
  }, [map, isReady, padding, aoi, candidateList]);
}
