"use client";

import { FORECAST_HORIZONS_H, type ForecastHorizonH } from "@/domain/forecast";
import { useHotkey } from "@/features/shell/hotkeys";
import { useMapLayersStore } from "@/state/map-layers-store";
import { useShellUiStore } from "@/state/shell-ui-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { stepHorizon } from "./drift-math";
import { useForecastUiStore } from "./forecast-ui-store";
import { togglePlayback, useHorizonPlayback } from "./use-horizon-playback";

const HORIZON_DIGIT_CODES = ["Digit1", "Digit2", "Digit3", "Digit4", "Digit5"] as const;

export function chooseHorizon(horizonH: ForecastHorizonH): void {
  useForecastUiStore.getState().setPlaying(false);
  useWorkspaceStore.getState().setForecastHorizon(horizonH);
}

export function stepHorizonBy(delta: 1 | -1): void {
  chooseHorizon(stepHorizon(useWorkspaceStore.getState().forecastHorizonH, delta));
}

const INTERACTIVE_SELECTOR =
  "button, a[href], summary, [role='button'], [role='radio'], [role='slider'], [role='switch'], [role='tab'], [role='checkbox']";

function toggleFromSpace(event: KeyboardEvent): void {
  if (event.target instanceof Element && event.target.closest(INTERACTIVE_SELECTOR)) return;
  event.preventDefault();
  togglePlayback();
}

function horizonForDigit(code: string): ForecastHorizonH | undefined {
  const index = HORIZON_DIGIT_CODES.indexOf(code as (typeof HORIZON_DIGIT_CODES)[number]);
  return index === -1 ? undefined : FORECAST_HORIZONS_H[index];
}

export function ForecastHotkeys({ enabled: available = true }: { enabled?: boolean }) {
  const sheetOpen = useShellUiStore((state) => state.shortcutSheetOpen);
  const enabled = available && !sheetOpen;
  const toggleParticlesPaused = useMapLayersStore((state) => state.toggleParticlesPaused);

  useHorizonPlayback(available);
  useHotkey("BracketLeft", () => stepHorizonBy(-1), { enabled });
  useHotkey("BracketRight", () => stepHorizonBy(1), { enabled });
  useHotkey(
    HORIZON_DIGIT_CODES,
    (event) => {
      const horizon = horizonForDigit(event.code);
      if (horizon !== undefined) chooseHorizon(horizon);
    },
    { enabled, shift: true },
  );
  useHotkey("Space", toggleFromSpace, { enabled, preventDefault: false });
  useHotkey("KeyM", toggleParticlesPaused, { enabled });
  return null;
}
