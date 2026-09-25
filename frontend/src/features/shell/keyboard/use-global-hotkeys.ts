"use client";

import { useRouter } from "next/navigation";
import { usePreferencesStore } from "@/state/preferences-store";
import { useShellUiStore } from "@/state/shell-ui-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { useHotkey, useKeyAlias } from "../hotkeys";
import {
  MODE_DIGIT_CODES,
  modeForDigitCode,
  modeHref,
  useActiveMode,
  useViewQuery,
} from "../orientation/modes";
import { closeTopEscapeLayer } from "./escape-stack";

type GlobalHotkeysOptions = {
  onToggleQueue: (() => void) | null;
};

function openShortcutSheet(): void {
  useShellUiStore.getState().setShortcutSheetOpen(true);
}

function releaseSelection(): boolean {
  const { selectedCandidateId, selectedTargetId, clearSelection } = useWorkspaceStore.getState();
  if (selectedCandidateId === null && selectedTargetId === null) return false;
  clearSelection();
  return true;
}

export function useGlobalHotkeys({ onToggleQueue }: GlobalHotkeysOptions): void {
  const router = useRouter();
  const activeMode = useActiveMode();
  const query = useViewQuery();
  const modalOpen = useShellUiStore((state) => state.shortcutSheetOpen);
  const toggleTheme = usePreferencesStore((state) => state.toggleTheme);
  const toggleDemo = useWorkspaceStore((state) => state.toggleDemoFixtures);
  const enabled = !modalOpen;

  useHotkey(
    MODE_DIGIT_CODES,
    (event) => {
      const mode = modeForDigitCode(event.code);
      if (mode && mode.id !== activeMode?.id) router.push(modeHref(mode, query));
    },
    { enabled },
  );
  useHotkey("KeyK", openShortcutSheet, { mod: true, enabled });
  useHotkey("Slash", openShortcutSheet, { shift: true, enabled });
  useKeyAlias("?", openShortcutSheet, { enabled });
  useHotkey("KeyT", toggleTheme, { enabled });
  useHotkey("KeyD", toggleDemo, { enabled });
  useHotkey("KeyQ", () => onToggleQueue?.(), { enabled: enabled && onToggleQueue !== null });
  useHotkey(
    "Escape",
    (event) => {
      if (event.defaultPrevented) return;
      if (closeTopEscapeLayer() || releaseSelection()) event.preventDefault();
    },
    { preventDefault: false },
  );
}
