"use client";

import { useMemo } from "react";
import { useCandidates } from "@/data/candidates";
import type { DebrisCandidate } from "@/domain/detection";
import { useHotkey } from "@/features/shell/hotkeys";
import { useUnacknowledgedCandidateIds } from "@/features/shell/queue/use-queue";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { orderByPriority, stepInOrder } from "./object-order";
import { useSelectObject } from "./use-select-object";

const EMPTY: readonly DebrisCandidate[] = [];

function useOrderedCandidates(): readonly DebrisCandidate[] {
  const sourced = useCandidates();
  const data = sourced.origin === "none" ? EMPTY : sourced.data;
  return useMemo(() => orderByPriority(data), [data]);
}

export function useObjectHotkeys(enabled: boolean): void {
  const ordered = useOrderedCandidates();
  const unacknowledged = useUnacknowledgedCandidateIds();
  const selectedId = useWorkspaceStore((state) => state.selectedCandidateId);
  const selectObject = useSelectObject();
  const setHint = useStatusHintStore((state) => state.setHint);
  const active = enabled && ordered.length > 0;

  const step = (delta: 1 | -1) => {
    const target = stepInOrder(ordered, selectedId, delta);
    if (target) selectObject(target);
  };

  const stepToUnacknowledged = () => {
    const target = stepInOrder(ordered, selectedId, 1, (candidate) =>
      unacknowledged.includes(candidate.id),
    );
    if (target) selectObject(target);
    else setHint("Неквитированных событий по объектам нет");
  };

  useHotkey("KeyJ", () => step(1), { enabled: active });
  useHotkey("KeyK", () => step(-1), { enabled: active });
  useHotkey("KeyJ", stepToUnacknowledged, { enabled: active, shift: true });
}
