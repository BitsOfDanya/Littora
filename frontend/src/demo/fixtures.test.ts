import { describe, expect, it } from "vitest";
import { DEMO_CANDIDATES } from "./candidates";
import { DEMO_FORECASTS } from "./forecast";
import { DEMO_SCENES } from "./scenes";
import { DEMO_TRACK } from "./timeline";

describe("demo fixtures stay internally consistent", () => {
  it("gives every candidate a positive FDI", () => {
    for (const candidate of DEMO_CANDIDATES) {
      expect(candidate.spectrum.indices.fdi).toBeGreaterThan(0);
    }
  });

  it("keeps coverage estimates ordered as low ≤ value ≤ high", () => {
    for (const { coverage } of DEMO_CANDIDATES) {
      expect(coverage.low).toBeLessThanOrEqual(coverage.value);
      expect(coverage.value).toBeLessThanOrEqual(coverage.high);
    }
  });

  it("derives pixel counts from 10 m pixels", () => {
    for (const candidate of DEMO_CANDIDATES) {
      expect(candidate.pixelCount).toBe(Math.max(1, Math.round(candidate.areaM2 / 100)));
    }
  });

  it("orders scenes chronologically and tracks only known scenes", () => {
    const times = DEMO_SCENES.map((scene) => Date.parse(scene.acquiredAt));
    expect(times).toEqual([...times].sort((a, b) => a - b));
    const sceneIds = new Set(DEMO_SCENES.map((scene) => scene.id));
    expect(DEMO_TRACK.every((observation) => sceneIds.has(observation.sceneId))).toBe(true);
  });

  it("provides an hourly median path up to +72 h", () => {
    for (const forecast of DEMO_FORECASTS) {
      expect(forecast.medianPath).toHaveLength(73);
      expect(forecast.envelopes.map((envelope) => envelope.horizonH)).toEqual([6, 12, 24, 48, 72]);
    }
  });
});
