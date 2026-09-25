import { describe, expect, it } from "vitest";
import { formatLatitude, formatLngLat, formatLongitude } from "./coordinates";

describe("coordinate formatting", () => {
  it("formats decimal degrees with Russian hemisphere suffixes", () => {
    expect(formatLatitude(15.95604)).toBe("15,9560° с. ш.");
    expect(formatLongitude(-88.16031)).toBe("88,1603° з. д.");
  });

  it("formats degrees and decimal minutes", () => {
    expect(formatLatitude(15.956, "dm")).toBe("15°57,36′ с. ш.");
    expect(formatLatitude(-29.05, "dm")).toBe("29°03,00′ ю. ш.");
  });

  it("formats degrees, minutes and seconds", () => {
    expect(formatLongitude(131.8525, "dms")).toBe("131°51′09,0″ в. д.");
  });

  it("puts latitude before longitude", () => {
    expect(formatLngLat([-88.25, 16])).toBe("16,0000° с. ш.  88,2500° з. д.");
  });
});
