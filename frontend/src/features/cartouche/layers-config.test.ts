import { describe, expect, it } from "vitest";
import {
  DEFAULT_VISIBLE_LAYERS,
  findLayer,
  LAYERS,
  layersForMode,
  resolveLayerId,
} from "@/config/layers";

describe("layer config", () => {
  it("keeps legacy ids working through aliases", () => {
    expect(resolveLayerId("currents")).toBe("particles");
    expect(resolveLayerId("drift-forecast")).toBe("forecast-envelopes");
    expect(findLayer("currents")?.label).toBe("Частицы течений");
  });

  it("has unique ids and only known default layers", () => {
    const ids = LAYERS.map((layer) => layer.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const id of DEFAULT_VISIBLE_LAYERS) expect(ids).toContain(id);
  });

  it("gives every capability-bound layer a reason for the planned state", () => {
    for (const layer of LAYERS)
      if (layer.capability) expect(layer.plannedReason, layer.id).toBeTruthy();
  });

  it("keeps the models mode free of map layers", () => {
    expect(layersForMode("models")).toEqual([]);
    expect(layersForMode("monitor").map((layer) => layer.id)).toContain("labels");
  });
});
