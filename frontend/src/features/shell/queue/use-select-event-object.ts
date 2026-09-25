"use client";

import { useCallback } from "react";
import { useCandidates } from "@/data/candidates";
import { easeToIfOutside } from "@/features/map/camera";
import { useMainMap } from "@/features/map/use-main-map";
import { useWorkspaceStore } from "@/state/workspace-store";

export function useSelectEventObject(): (candidateId: string) => void {
  const map = useMainMap();
  const candidates = useCandidates();
  const selectCandidate = useWorkspaceStore((state) => state.selectCandidate);
  const list = candidates.origin === "none" ? null : candidates.data;

  return useCallback(
    (candidateId: string) => {
      selectCandidate(candidateId);
      const candidate = list?.find((entry) => entry.id === candidateId);
      if (map && candidate) easeToIfOutside(map, candidate.centroid);
    },
    [map, list, selectCandidate],
  );
}
