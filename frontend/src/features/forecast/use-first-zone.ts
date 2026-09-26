"use client";

import { useEffect, useRef } from "react";
import { useDriftScenario } from "@/data/forecast";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { useAnalysisStore } from "@/state/analysis-store";
import { useWorkspaceStore } from "@/state/workspace-store";

export function useFirstZoneSelection(): void {
  const scenario = useDriftScenario();
  const selectCandidate = useWorkspaceStore((state) => state.selectCandidate);
  const setHint = useStatusHintStore((state) => state.setHint);
  const openedRef = useRef<string | null>(null);

  useEffect(() => {
    if (!scenario || openedRef.current === scenario.analysisId) return;
    openedRef.current = scenario.analysisId;
    const [first] = scenario.forecasts;
    if (!first) return;
    const wanted =
      useWorkspaceStore.getState().selectedCandidateId ?? useAnalysisStore.getState().zoneId;
    if (wanted && scenario.forecasts.some((forecast) => forecast.candidateId === wanted)) {
      selectCandidate(wanted);
      return;
    }
    selectCandidate(first.candidateId);
    if (wanted) setHint(`${wanted} не вошла в расчёт дрейфа — показана ${first.candidateId}`);
  }, [scenario, selectCandidate, setHint]);
}
