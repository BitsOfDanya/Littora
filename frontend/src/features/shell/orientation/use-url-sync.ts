"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import { AREAS_OF_INTEREST } from "@/config/aois";
import { useCandidates } from "@/data/candidates";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { ANALYSIS_ID_PATTERN } from "@/lib/api/analyses";
import { useAnalysisStore } from "@/state/analysis-store";
import { useWorkspaceStore } from "@/state/workspace-store";

const URL_WRITE_DEBOUNCE_MS = 400;

function validAoiId(value: string | null) {
  return AREAS_OF_INTEREST.find((aoi) => aoi.id === value)?.id;
}

function useUrlRead(): { current: boolean } {
  const candidates = useCandidates();
  const setAoi = useWorkspaceStore((state) => state.setAoi);
  const selectCandidate = useWorkspaceStore((state) => state.selectCandidate);
  const setHint = useStatusHintStore((state) => state.setHint);
  const setAnalysis = useAnalysisStore((state) => state.setAnalysis);
  const readRef = useRef(false);
  const pendingSelectionRef = useRef<string | null>(null);
  const pendingAnalysisRef = useRef<string | null>(null);

  useEffect(() => {
    if (!readRef.current) {
      readRef.current = true;
      const params = new URLSearchParams(window.location.search);
      pendingSelectionRef.current = params.get("sel");
      const analysisId = params.get("analysis");
      pendingAnalysisRef.current =
        analysisId && ANALYSIS_ID_PATTERN.test(analysisId) ? analysisId : null;
      const aoiId = validAoiId(params.get("aoi"));
      if (aoiId && aoiId !== useWorkspaceStore.getState().aoiId) {
        setAoi(aoiId);
        return;
      }
    }
    const pendingAnalysis = pendingAnalysisRef.current;
    if (pendingAnalysis) {
      pendingAnalysisRef.current = null;
      setAnalysis(pendingAnalysis);
    }
    const pending = pendingSelectionRef.current;
    if (!pending) return;
    pendingSelectionRef.current = null;
    const exists =
      candidates.origin !== "none" && candidates.data.some((candidate) => candidate.id === pending);
    const liveZone =
      candidates.origin !== "demo" && useAnalysisStore.getState().analysisId !== null;
    if (exists || liveZone) selectCandidate(pending);
    else setHint(`Объект ${pending} не найден в текущих данных`);
  }, [candidates, setAoi, selectCandidate, setHint, setAnalysis]);

  return readRef;
}

export function useUrlSync(): void {
  const readRef = useUrlRead();
  const pathname = usePathname();
  const aoiId = useWorkspaceStore((state) => state.aoiId);
  const selectedId = useWorkspaceStore((state) => state.selectedCandidateId);
  const analysisId = useAnalysisStore((state) => state.analysisId);

  useEffect(() => {
    if (!readRef.current) return;
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams(window.location.search);
      params.set("aoi", aoiId);
      if (selectedId) params.set("sel", selectedId);
      else params.delete("sel");
      if (analysisId) params.set("analysis", analysisId);
      else params.delete("analysis");
      const next = `${window.location.pathname}?${params.toString()}`;
      if (next !== `${window.location.pathname}${window.location.search}`)
        window.history.replaceState(null, "", next);
    }, URL_WRITE_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [readRef, aoiId, selectedId, analysisId, pathname]);
}
