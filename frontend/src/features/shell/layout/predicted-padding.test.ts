import { describe, expect, it } from "vitest";
import { type MonitorChrome, predictMonitorPadding } from "./predicted-padding";

const desktop: MonitorChrome = {
  width: 1440,
  height: 900,
  frameVisible: true,
  cartoucheCollapsed: undefined,
  sheetDetent: "closed",
  hasAlarmRow: true,
};

describe("predictMonitorPadding", () => {
  it("adds the frame, rail, status bar and the expanded cartouche at 1440", () => {
    expect(predictMonitorPadding(desktop)).toEqual({ top: 62, right: 18, bottom: 150, left: 334 });
  });

  it("moves the collapsed cartouche strip from the left inset to the top inset", () => {
    const padding = predictMonitorPadding({ ...desktop, cartoucheCollapsed: true });
    expect(padding.left).toBe(18);
    expect(padding.top).toBe(44 + 18 + 12 + 40);
  });

  it("uses laptop tokens at 1280", () => {
    expect(predictMonitorPadding({ ...desktop, width: 1280, height: 800 })).toEqual({
      top: 60,
      right: 16,
      bottom: 140,
      left: 316,
    });
  });

  it("adds the mode row on tablet portrait and collapses the cartouche by default", () => {
    expect(predictMonitorPadding({ ...desktop, width: 834, height: 1112 })).toEqual({
      top: 150,
      right: 14,
      bottom: 134,
      left: 14,
    });
  });

  it("reserves the tools column, stepper, tab bar and closed sheet on phone", () => {
    expect(predictMonitorPadding({ ...desktop, width: 390, height: 844 })).toEqual({
      top: 48,
      right: 56,
      bottom: 154,
      left: 0,
    });
  });

  it("drops the frame when the graticule is off", () => {
    expect(
      predictMonitorPadding({ ...desktop, frameVisible: false, cartoucheCollapsed: true }),
    ).toEqual({
      top: 96,
      right: 0,
      bottom: 132,
      left: 0,
    });
  });
});
