import { describe, expect, it } from "vitest";
import { GATE_RUN_MS, gateFrame, leafTransform, scaleTransform } from "./gate-choreography";

const frameAt = (run: Parameters<typeof gateFrame>[0]["run"], t: number, reducedMotion = false) =>
  gateFrame({ run, t, visible: true, reducedMotion });

describe("gate choreography", () => {
  it("rests closed over a dimmed, slightly enlarged map", () => {
    const idle = frameAt(null, 0);
    expect(idle.travel).toBe(0);
    expect(idle.scrimOpacity).toBeCloseTo(0.45);
    expect(idle.mapScale).toBeCloseTo(1.02);
    expect(frameAt(null, 0, true).mapScale).toBe(1);
  });

  it("equalises, unlatches, then travels in the full opening", () => {
    expect(frameAt("full", 320).equalised).toBe(1);
    expect(frameAt("full", 400).unlatchPx).toBeCloseTo(5);
    expect(frameAt("full", 400).travel).toBe(0);
    expect(frameAt("full", 1280).travel).toBe(1);
    expect(frameAt("full", 1300).scrimOpacity).toBe(0);
    expect(frameAt("full", 1300).mapScale).toBe(1);
    expect(frameAt("full", 1280).shadowOpacity).toBe(0);
    expect(GATE_RUN_MS.full).toBe(1400);
  });

  it("skips the gauge and unlatch on repeat openings", () => {
    expect(frameAt("repeat", 0).pointerOpacity).toBe(0);
    expect(frameAt("repeat", 440).travel).toBe(1);
    expect(GATE_RUN_MS.repeat).toBe(520);
  });

  it("fades without transforms under reduced motion", () => {
    const halfway = frameAt("fade", 80);
    expect(halfway.gateOpacity).toBeCloseTo(0.5);
    expect(halfway.travel).toBe(0);
    expect(halfway.mapScale).toBe(1);
    expect(halfway.scrimOpacity).toBe(0);
  });

  it("closes from fully open to shut", () => {
    expect(frameAt("close", 0).travel).toBe(1);
    expect(frameAt("close", 520).travel).toBe(0);
    expect(frameAt("close", 520).scrimOpacity).toBeCloseTo(0.45);
  });

  it("releases the map when the gate is hidden", () => {
    const hidden = gateFrame({ run: null, t: 0, visible: false, reducedMotion: false });
    expect(scaleTransform(hidden.mapScale)).toBe("none");
    expect(hidden.scrimOpacity).toBe(0);
  });

  it("moves leaves apart symmetrically", () => {
    const frame = frameAt("full", 400);
    expect(leafTransform("upper", frame)).toBe("translateY(calc(0.000% - 5.000px))");
    expect(leafTransform("lower", frame)).toBe("translateY(calc(0.000% + 5.000px))");
    expect(leafTransform("upper", frameAt(null, 0))).toBe("none");
  });
});
