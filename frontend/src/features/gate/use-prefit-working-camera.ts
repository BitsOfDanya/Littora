"use client";

import { useEffect } from "react";
import { findAoi } from "@/config/aois";
import { useCandidates } from "@/data/candidates";
import { fitDefaultOnce, isDefaultFitDone } from "@/features/map/camera";
import { useMapViewStore } from "@/features/map/state/map-view-store";
import { useMainMap } from "@/features/map/use-main-map";
import { predictMonitorPadding } from "@/features/shell/layout/predicted-padding";
import { useCartoucheStore } from "@/state/cartouche-store";
import { useLayerVisible } from "@/state/map-layers-store";
import { useShellUiStore } from "@/state/shell-ui-store";
import { useWorkspaceStore } from "@/state/workspace-store";

export function usePrefitWorkingCamera(): void {
  const map = useMainMap();
  const isReady = useMapViewStore((state) => state.isReady);
  const aoi = findAoi(useWorkspaceStore((state) => state.aoiId));
  const candidates = useCandidates();
  const candidateList = candidates.origin === "none" ? null : candidates.data;
  const frameVisible = useLayerVisible("graticule");

  useEffect(() => {
    if (isDefaultFitDone() || !map || !isReady || !aoi) return;
    const padding = predictMonitorPadding({
      width: window.innerWidth,
      height: window.innerHeight,
      frameVisible,
      cartoucheCollapsed: useCartoucheStore.getState().collapsedByMode.monitor,
      sheetDetent: useShellUiStore.getState().sheetDetent,
      hasAlarmRow: candidateList !== null,
    });
    fitDefaultOnce(map, { aoi, candidates: candidateList }, { durationMs: 0, padding });
  }, [map, isReady, aoi, candidateList, frameVisible]);
}
