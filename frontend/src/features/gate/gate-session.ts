import { type GateRun } from "./gate-choreography";
import { prefersReducedMotionNow } from "./gate-store";

const OPENED_KEY = "littora.gate.opened";

function hasOpenedThisSession(): boolean {
  try {
    return window.sessionStorage.getItem(OPENED_KEY) === "1";
  } catch {
    return false;
  }
}

export function rememberOpened(): void {
  try {
    window.sessionStorage.setItem(OPENED_KEY, "1");
  } catch {
    return;
  }
}

export function chooseOpeningRun(): GateRun {
  if (prefersReducedMotionNow()) return "fade";
  return hasOpenedThisSession() ? "repeat" : "full";
}
