"use client";

import { useCallback } from "react";
import type { RealZone } from "@/features/analysis/zones";
import { useMapMode } from "@/features/cartouche/use-map-mode";
import { useMainMap } from "@/features/map/use-main-map";
import { useAnalysisStore } from "@/state/analysis-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { revealInVisibleField } from "./visible-field";

export function useSelectZone(): { selectedId: string | null; select: (zone: RealZone) => void } {
  const map = useMainMap();
  const mode = useMapMode();
  const zoneId = useAnalysisStore((state) => state.zoneId);
  const selectZone = useAnalysisStore((state) => state.selectZone);
  const candidateId = useWorkspaceStore((state) => state.selectedCandidateId);
  const selectCandidate = useWorkspaceStore((state) => state.selectCandidate);
  const forecast = mode === "forecast";

  const select = useCallback(
    (zone: RealZone) => {
      if (forecast) selectCandidate(zone.id);
      else selectZone(zone.id);
      if (map && zone.centroid) revealInVisibleField(map, [...zone.centroid]);
    },
    [forecast, map, selectCandidate, selectZone],
  );

  return { selectedId: forecast ? candidateId : zoneId, select };
}
