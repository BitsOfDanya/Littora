import type { SheetDetent } from "@/state/shell-ui-store";

export const SHEET_CLOSED_PX = 44;
const SHEET_PEEK_PX = 232;
const ALARM_ROW_PX = 32;
const FULL_GAP_PX = 8;
const FLICK_PX_PER_MS = 0.45;

export const DETENT_ORDER: readonly SheetDetent[] = ["closed", "peek", "half", "full"];

export const DETENT_LABEL: Record<SheetDetent, string> = {
  closed: "свёрнута",
  peek: "низкая",
  half: "половина экрана",
  full: "во весь экран",
};

export type DetentHeights = Record<SheetDetent, number>;

const clamp = (value: number, min: number, max: number) =>
  Math.min(Math.max(value, min), Math.max(min, max));

export function detentHeights(available: number, hasAlarmRow: boolean): DetentHeights {
  const full = Math.max(SHEET_CLOSED_PX, available - FULL_GAP_PX);
  const half = clamp(Math.round(available / 2), SHEET_CLOSED_PX, full);
  const peek = clamp(SHEET_PEEK_PX + (hasAlarmRow ? ALARM_ROW_PX : 0), SHEET_CLOSED_PX, half);
  return { closed: SHEET_CLOSED_PX, peek, half, full };
}

export function nextDetentOnTap(detent: SheetDetent): SheetDetent {
  if (detent === "full") return "peek";
  return DETENT_ORDER[DETENT_ORDER.indexOf(detent) + 1];
}

export function stepDetent(detent: SheetDetent, direction: 1 | -1): SheetDetent {
  const index = Math.min(
    DETENT_ORDER.length - 1,
    Math.max(0, DETENT_ORDER.indexOf(detent) + direction),
  );
  return DETENT_ORDER[index];
}

export function detentForRelease(
  height: number,
  velocity: number,
  heights: DetentHeights,
): SheetDetent {
  if (velocity > FLICK_PX_PER_MS) {
    const below = [...DETENT_ORDER].reverse().find((detent) => heights[detent] < height - 1);
    return below ?? "closed";
  }
  if (velocity < -FLICK_PX_PER_MS) {
    const above = DETENT_ORDER.find((detent) => heights[detent] > height + 1);
    return above ?? "full";
  }
  return DETENT_ORDER.reduce((nearest, detent) =>
    Math.abs(heights[detent] - height) < Math.abs(heights[nearest] - height) ? detent : nearest,
  );
}

export function clampSheetHeight(height: number, heights: DetentHeights): number {
  return clamp(height, heights.closed, heights.full);
}
