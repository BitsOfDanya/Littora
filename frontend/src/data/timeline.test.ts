import { describe, expect, it } from "vitest";
import { DEMO_CANDIDATES } from "@/demo/candidates";
import { DEMO_SCENES } from "@/demo/scenes";
import {
  DEMO_CANDIDATE_HISTORIES,
  DEMO_HISTORY_SEEDS,
  DEMO_TRACK,
  DEMO_TRACKED_CANDIDATE_ID,
} from "@/demo/timeline";
import { toLocalMeters } from "@/lib/geo/local-metric";

const usableIndexes = DEMO_SCENES.flatMap((scene, index) =>
  scene.usability === "usable" ? [index] : [],
);

describe("demo candidate histories", () => {
  it("seeds one state per scene and marks unusable scenes as no data", () => {
    for (const seed of Object.values(DEMO_HISTORY_SEEDS)) {
      expect(seed.states).toHaveLength(DEMO_SCENES.length);
      DEMO_SCENES.forEach((scene, index) => {
        expect(seed.states[index] === "n").toBe(scene.usability === "unusable");
        if (scene.usability === "usable") expect(["o", "-"]).toContain(seed.states[index]);
      });
    }
  });

  it("ends every history at the candidate as detected on the latest scene", () => {
    for (const candidate of DEMO_CANDIDATES) {
      const history = DEMO_CANDIDATE_HISTORIES.find((entry) => entry.candidateId === candidate.id);
      const last = history?.passes.at(-1);
      expect(last?.state).toBe("found");
      expect(last?.geometry).toBe(candidate.geometry);
      expect(last?.coverage).toEqual(candidate.coverage);
    }
  });

  it("matches the persistence claimed by the candidate fixture", () => {
    for (const candidate of DEMO_CANDIDATES) {
      const history = DEMO_CANDIDATE_HISTORIES.find((entry) => entry.candidateId === candidate.id);
      const found = usableIndexes.filter((index) => history?.passes[index].state === "found");
      expect(found).toHaveLength(candidate.persistence.detectedIn);
      expect(usableIndexes).toHaveLength(candidate.persistence.usablePasses);
    }
  });

  it("reproduces the change since the previous pass", () => {
    for (const candidate of DEMO_CANDIDATES) {
      const history = DEMO_CANDIDATE_HISTORIES.find((entry) => entry.candidateId === candidate.id);
      const previousIndex = DEMO_SCENES.length - 3;
      const previous = history?.passes[previousIndex];
      if (!candidate.change) {
        expect(previous?.state).not.toBe("found");
        continue;
      }
      expect(previous?.sceneId).toBe(candidate.change.previousSceneId);
      expect(previous?.state).toBe("found");
      const areaRatio = candidate.areaM2 / (previous?.areaM2 ?? 1) - 1;
      expect(areaRatio).toBeCloseTo(candidate.change.areaDeltaRatio, 1);
      const coverageDelta = (candidate.coverage.value - (previous?.coverage?.value ?? 0)) * 100;
      expect(coverageDelta).toBeCloseTo(candidate.change.coverageDeltaPoints, 0);
      const [east, north] = toLocalMeters(previous?.centroid ?? [0, 0], candidate.centroid);
      expect(Math.hypot(east, north)).toBeCloseTo(candidate.change.displacementM, -2);
    }
  });

  it("keeps coverage intervals ordered", () => {
    for (const history of DEMO_CANDIDATE_HISTORIES)
      for (const pass of history.passes) {
        if (!pass.coverage) continue;
        expect(pass.coverage.low).toBeLessThanOrEqual(pass.coverage.value);
        expect(pass.coverage.value).toBeLessThanOrEqual(pass.coverage.high);
      }
  });

  it("derives the legacy track from the tracked history without cloudy passes", () => {
    expect(DEMO_TRACKED_CANDIDATE_ID).toBe(DEMO_CANDIDATES[0].id);
    expect(DEMO_TRACK.length).toBeGreaterThan(0);
    for (const observation of DEMO_TRACK)
      expect(observation.detected).toBe(observation.geometry !== null);
  });
});
