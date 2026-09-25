import { describe, expect, it } from "vitest";
import { aggregateHotspots } from "./hotspots";
import { candidateLabel, shortCandidateId, soundingText } from "./label-text";

describe("candidate label text", () => {
  it("shortens the full id to the serial", () => {
    expect(shortCandidateId("LT-260918-004")).toBe("LT-004");
    expect(shortCandidateId("custom")).toBe("custom");
  });

  it("writes coverage as a sounding with the tenth as a subscript", () => {
    expect(soundingText(0.124)).toBe("12₄");
    expect(soundingText(0.21)).toBe("21₀");
    expect(soundingText(0.0049)).toBe("0₅");
    expect(soundingText(0.1996)).toBe("20₀");
  });

  it("joins id and sounding", () => {
    expect(candidateLabel("LT-260918-001", 0.124)).toBe("LT-001 12₄");
  });
});

describe("hotspot grid", () => {
  it("averages cell coverage inside one kilometre cell and ranks candidates", () => {
    const cells = aggregateHotspots([
      { candidateId: "a", center: [-88.2, 15.8], coverage: 0.2 },
      { candidateId: "a", center: [-88.2001, 15.8001], coverage: 0.1 },
      { candidateId: "b", center: [-88.2002, 15.8], coverage: 0.36 },
    ]);
    expect(cells).toHaveLength(1);
    expect(cells[0].coverage).toBeCloseTo(0.22, 5);
    expect(cells[0].cellCount).toBe(3);
    expect(cells[0].candidateIds).toEqual(["b", "a"]);
    expect(cells[0].polygon).toHaveLength(4);
  });

  it("splits cells that are more than a kilometre apart", () => {
    const cells = aggregateHotspots([
      { candidateId: "a", center: [-88.2, 15.8], coverage: 0.2 },
      { candidateId: "a", center: [-88.1, 15.8], coverage: 0.2 },
    ]);
    expect(cells).toHaveLength(2);
  });

  it("returns nothing for no cells", () => {
    expect(aggregateHotspots([])).toEqual([]);
  });
});
