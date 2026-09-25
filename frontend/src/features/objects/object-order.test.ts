import { describe, expect, it } from "vitest";
import type { DebrisCandidate } from "@/domain/detection";
import { orderByPriority, stepInOrder } from "./object-order";
import { pluralRu } from "./plural";

function candidate(
  id: string,
  priority: DebrisCandidate["priority"],
  score: number,
): DebrisCandidate {
  return { id, priority, confidence: { class: "likely", score } } as DebrisCandidate;
}

const CANDIDATES = [
  candidate("C", "medium", 0.9),
  candidate("A", "high", 0.7),
  candidate("D", "low", 0.95),
  candidate("B", "high", 0.8),
];

describe("object order", () => {
  it("sorts by priority, then by score", () => {
    expect(orderByPriority(CANDIDATES).map((entry) => entry.id)).toEqual(["B", "A", "C", "D"]);
  });

  it("steps forward and backward with wrap-around", () => {
    const ordered = orderByPriority(CANDIDATES);
    expect(stepInOrder(ordered, null, 1)?.id).toBe("B");
    expect(stepInOrder(ordered, null, -1)?.id).toBe("D");
    expect(stepInOrder(ordered, "D", 1)?.id).toBe("B");
    expect(stepInOrder(ordered, "B", -1)?.id).toBe("D");
  });

  it("skips objects the filter rejects", () => {
    const ordered = orderByPriority(CANDIDATES);
    expect(stepInOrder(ordered, "B", 1, (entry) => entry.id === "D")?.id).toBe("D");
    expect(stepInOrder(ordered, "B", 1, () => false)).toBeUndefined();
  });
});

describe("russian plurals", () => {
  it("picks the form by the last digits", () => {
    const forms = ["кандидат", "кандидата", "кандидатов"] as const;
    expect([1, 2, 5, 11, 21, 22, 112].map((count) => pluralRu(count, forms))).toEqual([
      "кандидат",
      "кандидата",
      "кандидатов",
      "кандидатов",
      "кандидат",
      "кандидата",
      "кандидатов",
    ]);
  });
});
