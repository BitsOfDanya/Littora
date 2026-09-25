import { describe, expect, it } from "vitest";
import { DEMO_CANDIDATES } from "./candidates";
import { DEMO_SCENE_CONDITIONS, nearestNoDataM } from "./masks";
import { DEMO_REFERENCE_SPECTRA, referenceAtCoverage } from "./references";
import { DEMO_SCENES } from "./scenes";
import { DEMO_CANDIDATE_HISTORIES } from "./timeline";

describe("scene conditions fixture", () => {
  it("has conditions and a footprint for every scene", () => {
    for (const scene of DEMO_SCENES) {
      const conditions = DEMO_SCENE_CONDITIONS[scene.id];
      expect(conditions).toBeDefined();
      expect(conditions.footprint.coordinates[0]).toHaveLength(5);
    }
  });

  it("never hides an object that the history says was observed, and covers cloudy ones", () => {
    for (const history of DEMO_CANDIDATE_HISTORIES) {
      const candidate = DEMO_CANDIDATES.find((entry) => entry.id === history.candidateId);
      if (!candidate) continue;
      for (const pass of history.passes) {
        const distance = nearestNoDataM(pass.sceneId, pass.centroid ?? candidate.centroid);
        if (pass.state === "found" || pass.state === "not-found")
          expect(distance ?? Infinity).toBeGreaterThan(0);
        else expect(distance).toBe(0);
      }
    }
  });

  it("keeps the latest scene mostly clear", () => {
    const latest = DEMO_SCENES.at(-1);
    const conditions = latest ? DEMO_SCENE_CONDITIONS[latest.id] : undefined;
    expect(conditions?.noData.length).toBeGreaterThan(0);
    expect(conditions?.noData.every((area) => area.polygon.coordinates.length === 1)).toBe(true);
  });
});

describe("reference spectra", () => {
  it("mix toward water as coverage falls", () => {
    const plastic = DEMO_REFERENCE_SPECTRA.find((entry) => entry.key === "plastic");
    const water = DEMO_REFERENCE_SPECTRA.find((entry) => entry.key === "water");
    if (!plastic || !water) throw new Error("missing references");
    const none = referenceAtCoverage(plastic, 0);
    const nir = (bands: typeof none) => bands.find((band) => band.band === "B08")?.reflectance;
    expect(nir(none)).toBe(nir(referenceAtCoverage(water, 0.5)));
    expect(nir(referenceAtCoverage(plastic, 0.2)) ?? 0).toBeGreaterThan(nir(none) ?? 0);
  });
});
