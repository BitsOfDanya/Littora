import {
  cartoucheWidthFor,
  frameWidthFor,
  PHONE_MAX_WIDTH,
} from "@/features/map/furniture/use-frame-width";
import type { Padding } from "@/features/map/use-viewport-padding";
import { detentHeights } from "../phone/sheet-detents";

const TOP_BAR_PX = 44;
const PHONE_TOP_BAR_PX = 48;
const TABLET_MODE_ROW_PX = 40;
const STATUS_BAR_PX = 24;
const PHONE_TAB_BAR_PX = 58;
const PHONE_STEPPER_PX = 52;
const PHONE_TOOLS_PX = 56;
const FURNITURE_GAP_PX = 12;
const CARTOUCHE_STRIP_PX = 40;
const TABLET_MAX_WIDTH = 1023;
const LAPTOP_MIN_WIDTH = 1280;
const DESKTOP_MIN_WIDTH = 1440;

export type MonitorChrome = {
  width: number;
  height: number;
  frameVisible: boolean;
  cartoucheCollapsed: boolean | undefined;
  sheetDetent: "closed" | "peek" | "half" | "full";
  hasAlarmRow: boolean;
};

function railHeightFor(width: number): number {
  if (width >= DESKTOP_MIN_WIDTH) return 108;
  if (width > TABLET_MAX_WIDTH) return 100;
  return 96;
}

function phonePadding({
  width,
  height,
  frameVisible,
  sheetDetent,
  hasAlarmRow,
}: MonitorChrome): Padding {
  const frame = frameVisible ? frameWidthFor(width) : 0;
  const docked = PHONE_TAB_BAR_PX + PHONE_STEPPER_PX;
  const available = height - PHONE_TOP_BAR_PX - docked;
  const sheet = detentHeights(available, hasAlarmRow)[sheetDetent];
  return {
    top: PHONE_TOP_BAR_PX + frame,
    right: Math.max(frame, PHONE_TOOLS_PX),
    bottom: docked + Math.max(frame, sheet),
    left: frame,
  };
}

export function predictMonitorPadding(chrome: MonitorChrome): Padding {
  const { width, frameVisible, cartoucheCollapsed } = chrome;
  if (width <= PHONE_MAX_WIDTH) return phonePadding(chrome);
  const frame = frameVisible ? frameWidthFor(width) : 0;
  const isTablet = width <= TABLET_MAX_WIDTH;
  const cartoucheOpen = !(cartoucheCollapsed ?? width < LAPTOP_MIN_WIDTH);
  const cartoucheEdge = frame + FURNITURE_GAP_PX;
  const left = cartoucheOpen ? cartoucheEdge + cartoucheWidthFor(width) : frame;
  const top = cartoucheOpen ? frame : cartoucheEdge + CARTOUCHE_STRIP_PX;
  return {
    top: TOP_BAR_PX + (isTablet ? TABLET_MODE_ROW_PX : 0) + top,
    right: frame,
    bottom: railHeightFor(width) + STATUS_BAR_PX + frame,
    left,
  };
}
