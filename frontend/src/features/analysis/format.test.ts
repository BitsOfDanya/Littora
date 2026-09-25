import { describe, expect, it } from "vitest";
import { concentrationWithUnit, dayOffset, formatConcentration, formatDelta } from "./format";

describe("analysis formatting", () => {
  it("keeps precision proportional to the concentration", () => {
    expect(formatConcentration(null)).toBe("—");
    expect(formatConcentration(192.54)).toBe("193");
    expect(formatConcentration(60)).toBe("60,0");
    expect(formatConcentration(0.5)).toBe("0,50");
    expect(concentrationWithUnit(null)).toBe("нет значения");
  });

  it("counts whole days between survey and scene dates", () => {
    expect(dayOffset("2024-06-02T08:46:13.024Z", "2024-06-02")).toBe(0);
    expect(dayOffset("2024-06-02", "2024-06-05")).toBe(3);
    expect(dayOffset("2024-06-05", "2024-06-02")).toBe(-3);
    expect(formatDelta(0)).toBe("в день снимка");
    expect(formatDelta(-2)).toBe("−2 сут");
    expect(formatDelta(null)).toBe("дата неизвестна");
  });
});
