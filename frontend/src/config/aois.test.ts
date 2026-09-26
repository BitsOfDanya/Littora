import { describe, expect, it } from "vitest";
import { AREAS_OF_INTEREST, findAoi } from "./aois";

const RUSSIAN_SOUTH = [
  "novorossiysk",
  "anapa",
  "kerch-strait",
  "tuapse",
  "sochi",
  "don-delta",
  "kuban-mouth",
  "yeysk",
];

const inside = ([lng, lat]: readonly [number, number], bbox: readonly number[]) =>
  lng >= bbox[0] && lng <= bbox[2] && lat >= bbox[1] && lat <= bbox[3];

describe("areas of interest", () => {
  it("lists the Black Sea and Sea of Azov areas", () => {
    for (const id of RUSSIAN_SOUTH) expect(findAoi(id)?.group).toBe("russian-seas");
    expect(findAoi("neva-bay")).toBeDefined();
    expect(findAoi("doors-west")).toBeDefined();
  });

  it("keeps ids unique and every view and label inside its area", () => {
    const ids = AREAS_OF_INTEREST.map((aoi) => aoi.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const id of RUSSIAN_SOUTH) {
      const aoi = findAoi(id);
      if (!aoi) continue;
      expect(inside(aoi.center, aoi.bbox)).toBe(true);
      for (const label of aoi.waterLabels) expect(inside(label.position, aoi.bbox)).toBe(true);
      expect(aoi.bbox[2] - aoi.bbox[0]).toBeLessThanOrEqual(0.4);
      expect(aoi.sentinel2Tiles.length).toBe(1);
    }
  });
});
