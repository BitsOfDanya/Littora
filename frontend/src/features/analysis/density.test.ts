import { describe, expect, it } from "vitest";
import { densityCells, densityClass } from "./density";
import type { RealZone } from "./zones";

function zone(
  id: string,
  lon: number,
  lat: number,
  area: number,
  flags: RealZone["flags"] = [],
): RealZone {
  return {
    id,
    rank: 1,
    geometry: null,
    centroid: [lon, lat],
    pixels: 4,
    areaM2: 400,
    probabilityMax: 0.9,
    probabilityMean: 0.8,
    scl: null,
    flags,
    stability: null,
    coverage: {
      mean: 0.1,
      low: 0.05,
      high: 0.2,
      area_m2: area,
      area_m2_low: null,
      area_m2_high: null,
    },
  };
}

describe("density grid", () => {
  it("sums material area per square kilometre and skips ship-like zones", () => {
    const cells = densityCells([
      zone("a", 37.8001, 44.7001, 30),
      zone("b", 37.8002, 44.7002, 25),
      zone("c", 37.8003, 44.7003, 500, [{ kind: "vessel", label: "вероятно судно", evidence: [] }]),
    ]);
    expect(cells).toHaveLength(1);
    expect(cells[0].m2PerKm2).toBe(55);
    expect(cells[0].zones).toBe(2);
    expect(cells[0].densityClass.label).toBe("высокое");
  });

  it("uses the same classes as the legend", () => {
    expect(densityClass(10).label).toBe("низкое");
    expect(densityClass(20).label).toBe("умеренное");
    expect(densityClass(150).label).toBe("очень высокое");
  });
});
