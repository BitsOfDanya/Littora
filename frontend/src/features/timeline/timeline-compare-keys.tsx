"use client";

import { useEffect } from "react";
import type { SceneSummary } from "@/domain/scene";
import { useHotkey } from "@/features/shell/hotkeys";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { useShellUiStore } from "@/state/shell-ui-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { defaultPairIds, type DividerAction, nextDividerPosition } from "./compare-model";
import { useCompareActions, useCompareData } from "./use-compare";
import { usePlaybackController, useTogglePlayback } from "./use-playback";

const METHOD_HINT = "Способ сравнения: работает «Шторка» · «Прозрачность» и «Линза» в плане";

function moveDivider(action: DividerAction, large: boolean): void {
  const { compare, updateCompare } = useWorkspaceStore.getState();
  updateCompare({ position: nextDividerPosition(compare.position, action, large) });
}

function useDefaultPair(scenes: readonly SceneSummary[]): void {
  const hasPair = useWorkspaceStore((state) =>
    Boolean(state.compare.beforeSceneId && state.compare.afterSceneId),
  );
  useEffect(() => {
    if (hasPair) return;
    const ids = defaultPairIds(scenes);
    if (ids) useWorkspaceStore.getState().updateCompare(ids);
  }, [hasPair, scenes]);
}

export function TimelineCompareKeys() {
  const data = useCompareData();
  const actions = useCompareActions(data.scenes, data.pair);
  const togglePlayback = useTogglePlayback(data, actions);
  const modalOpen = useShellUiStore((state) => state.shortcutSheetOpen);
  const setHint = useStatusHintStore((state) => state.setHint);
  const enabled = !modalOpen;
  const stepping = enabled && data.pair !== null && data.enoughUsable;

  useDefaultPair(data.scenes);
  usePlaybackController(data, actions);

  useHotkey("KeyX", actions.swap, { enabled: enabled && data.pair !== null });
  useHotkey("Comma", () => moveDivider("decrease", false), { enabled });
  useHotkey("Period", () => moveDivider("increase", false), { enabled });
  useHotkey("Comma", () => moveDivider("decrease", true), { enabled, shift: true });
  useHotkey("Period", () => moveDivider("increase", true), { enabled, shift: true });
  useHotkey("KeyC", () => setHint(METHOD_HINT), { enabled });
  useHotkey("BracketLeft", () => actions.step("b", -1), { enabled: stepping });
  useHotkey("BracketRight", () => actions.step("b", 1), { enabled: stepping });
  useHotkey("BracketLeft", () => actions.step("b", -1, true), { enabled: stepping, shift: true });
  useHotkey("BracketRight", () => actions.step("b", 1, true), { enabled: stepping, shift: true });
  useHotkey("Space", togglePlayback, { enabled: stepping });
  return null;
}
