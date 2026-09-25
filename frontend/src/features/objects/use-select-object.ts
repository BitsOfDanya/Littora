"use client";

import { useCallback } from "react";
import type { DebrisCandidate } from "@/domain/detection";
import { useMainMap } from "@/features/map/use-main-map";
import { useWorkspaceStore } from "@/state/workspace-store";
import { revealInVisibleField } from "./visible-field";

export function useSelectObject(): (candidate: DebrisCandidate) => void {
  const map = useMainMap();
  const selectCandidate = useWorkspaceStore((state) => state.selectCandidate);
  return useCallback(
    (candidate: DebrisCandidate) => {
      selectCandidate(candidate.id);
      if (map) revealInVisibleField(map, candidate.centroid);
    },
    [map, selectCandidate],
  );
}
