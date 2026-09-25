import { describe, expect, it } from "vitest";
import { chipTiles, chipView, metersPerPixel, projectToChip, tileUrl } from "./evidence-view";

const windrow: [number, number][] = [
  [-88.225, 15.788],
  [-88.26, 15.8],
  [-88.26, 15.806],
];

describe("evidence chip view", () => {
  it("centres the object and keeps it inside the chip", () => {
    const view = chipView(windrow, 360, 176);
    for (const point of windrow) {
      const [x, y] = projectToChip(view, point);
      expect(x).toBeGreaterThan(0);
      expect(x).toBeLessThan(360);
      expect(y).toBeGreaterThan(0);
      expect(y).toBeLessThan(176);
    }
  });

  it("shows at least the minimum span so the 1 km scale bar fits", () => {
    const view = chipView(
      [
        [-88.2, 15.8],
        [-88.1999, 15.8001],
      ],
      360,
      176,
    );
    expect(metersPerPixel(15.8, view.zoom) * 360).toBeGreaterThanOrEqual(1599);
  });

  it("never asks for tiles above the source maximum zoom", () => {
    const view = chipView(
      [
        [-88.2, 15.8],
        [-88.1999, 15.8001],
      ],
      360,
      176,
      { minSpanM: 200 },
    );
    expect(view.tileZoom).toBe(14);
  });

  it("covers the whole chip with tiles", () => {
    const view = chipView(windrow, 360, 176);
    const tiles = chipTiles(view);
    const left = Math.min(...tiles.map((tile) => tile.left));
    const top = Math.min(...tiles.map((tile) => tile.top));
    const right = Math.max(...tiles.map((tile) => tile.left + tile.size));
    const bottom = Math.max(...tiles.map((tile) => tile.top + tile.size));
    expect(left).toBeLessThanOrEqual(0);
    expect(top).toBeLessThanOrEqual(0);
    expect(right).toBeGreaterThanOrEqual(360);
    expect(bottom).toBeGreaterThanOrEqual(176);
  });

  it("fills an XYZ template", () => {
    expect(
      tileUrl("https://t/{z}/{y}/{x}.jpg", { x: 3, y: 5, z: 7, left: 0, top: 0, size: 256 }),
    ).toBe("https://t/7/5/3.jpg");
  });
});
