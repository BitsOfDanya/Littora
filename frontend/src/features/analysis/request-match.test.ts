import { describe, expect, it } from "vitest";
import type { AnalysisCreate } from "@/lib/api/analyses";
import { roundBbox, spanTooLarge } from "./area";
import { matchesRequest } from "./use-analysis";

const saved = {
  request: {
    aoi_id: "doors-west",
    aoi_name: "Разрезы T1–T2",
    bbox: [29.45, 43.45, 30, 43.72] as [number, number, number, number],
    date: "2024-06-02",
    window_days: 1,
    scene_id: "S2A_T35TQJ_20240602T084613_L2A",
    target: "litter-visual",
  },
};

const draft: AnalysisCreate = {
  bbox: [29.45, 43.45, 30, 43.72],
  date: "2024-06-02",
  window_days: 1,
  aoi_id: "doors-west",
  scene_id: "S2A_T35TQJ_20240602T084613_L2A",
  target: null,
};

describe("saved analysis lookup", () => {
  it("treats an unset target as the primary one", () => {
    expect(matchesRequest(saved, draft, "litter-visual")).toBe(true);
    expect(matchesRequest(saved, { ...draft, target: "plastic-visual" }, "litter-visual")).toBe(
      false,
    );
  });

  it("requires the same scene, window and area", () => {
    expect(matchesRequest(saved, { ...draft, window_days: 3 }, "litter-visual")).toBe(false);
    expect(matchesRequest(saved, { ...draft, scene_id: null }, "litter-visual")).toBe(false);
    expect(
      matchesRequest(saved, { ...draft, bbox: [29.4, 43.45, 30, 43.72] }, "litter-visual"),
    ).toBe(false);
  });

  it("rounds and bounds requested areas", () => {
    expect(roundBbox([29.123456, 43.000049, 29.5, 43.99999])).toEqual([29.1235, 43, 29.5, 44]);
    expect(spanTooLarge([29, 43, 30, 44])).toBe(false);
    expect(spanTooLarge([29, 43, 30.5, 44])).toBe(true);
  });
});
