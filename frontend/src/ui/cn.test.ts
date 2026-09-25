import { describe, expect, it } from "vitest";
import { cn } from "./cn";

describe("cn", () => {
  it("lets later token colours override earlier ones", () => {
    expect(
      cn(
        "text-text-secondary hover:text-text-primary",
        "text-text-inverse hover:text-text-inverse",
      ),
    ).toBe("text-text-inverse hover:text-text-inverse");
  });

  it("keeps arbitrary font sizes separate from text colours", () => {
    expect(cn("text-[12px] text-text-secondary", "text-text-primary")).toBe(
      "text-[12px] text-text-primary",
    );
  });

  it("resolves border colour conflicts", () => {
    expect(cn("border border-line-control", "border-accent-selection")).toBe(
      "border border-accent-selection",
    );
  });
});
