"use client";

import { useCandidates } from "@/data/candidates";
import type { LngLat } from "@/domain/geo";
import { useWorkspaceStore } from "@/state/workspace-store";

export function useSelectionFocus(): LngLat | null {
  const selectedId = useWorkspaceStore((state) => state.selectedCandidateId);
  const candidates = useCandidates();
  if (!selectedId || candidates.origin === "none") return null;
  return candidates.data.find((candidate) => candidate.id === selectedId)?.centroid ?? null;
}
