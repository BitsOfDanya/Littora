"use client";

import { type MouseEvent, useCallback } from "react";
import { useGateStore } from "./gate-store";

function isPlainClick(event: MouseEvent<HTMLElement>): boolean {
  return (
    !event.defaultPrevented &&
    event.button === 0 &&
    !event.metaKey &&
    !event.ctrlKey &&
    !event.shiftKey &&
    !event.altKey
  );
}

export function useReturnToGate(): (event?: MouseEvent<HTMLElement>) => void {
  const beginClosing = useGateStore((state) => state.beginClosing);
  return useCallback(
    (event) => {
      if (event && !isPlainClick(event)) return;
      if (beginClosing()) event?.preventDefault();
    },
    [beginClosing],
  );
}
