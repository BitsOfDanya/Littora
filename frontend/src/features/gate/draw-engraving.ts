import type { Map as MapLibreMap } from "maplibre-gl";
import { GATE_LIVERY } from "./gate-livery";
import { chequerParity, planTicks, tickLabel, ticksInRange } from "./graticule-ticks";

export type LeafSide = "upper" | "lower";

export type EngravingGeometry = {
  side: LeafSide;
  width: number;
  height: number;
  top: number;
  rootHeight: number;
  frame: number;
  gaugeColumn: number;
  fontFamily: string;
};

type Box = { left: number; right: number; top: number; bottom: number };

type Axes = {
  xOf: (minutes: number) => number;
  yOf: (minutes: number) => number;
  lonMinutes: (step: number) => number[];
  latMinutes: (step: number) => number[];
  minorMin: number;
  majorMin: number;
};

const CHEQUER_PX = 4;
const LABEL_FONT_PX = 10.5;
const LABEL_EDGE_GAP_PX = 18;
const NORTH_UP_TOLERANCE_DEG = 0.5;

const crisp = (value: number) => Math.round(value) + 0.5;

function interiorOf({ side, width, height, frame, gaugeColumn }: EngravingGeometry): Box {
  return {
    left: frame,
    right: width - gaugeColumn - frame,
    top: side === "upper" ? frame : 0,
    bottom: side === "upper" ? height : height - frame,
  };
}

function isNorthUp(map: MapLibreMap): boolean {
  return (
    Math.abs(map.getBearing()) <= NORTH_UP_TOLERANCE_DEG && map.getPitch() <= NORTH_UP_TOLERANCE_DEG
  );
}

function axesFor(map: MapLibreMap, geometry: EngravingGeometry, scale: number): Axes {
  const centre = map.getCenter();
  const origin = map.project([centre.lng, centre.lat]);
  const pxPerMinute = Math.abs(map.project([centre.lng + 1 / 60, centre.lat]).x - origin.x);
  const { minorMin, majorMin } = planTicks(pxPerMinute);
  const centreX = geometry.width / 2;
  const centreY = geometry.rootHeight / 2;
  const toMap = (screen: number, pivot: number) => pivot + (screen - pivot) / scale;
  const middleY = toMap(geometry.top + geometry.height / 2, centreY);
  const west = map.unproject([toMap(0, centreX), middleY]).lng;
  const east = map.unproject([toMap(geometry.width, centreX), middleY]).lng;
  const north = map.unproject([centreX, toMap(geometry.top, centreY)]).lat;
  const south = map.unproject([centreX, toMap(geometry.top + geometry.height, centreY)]).lat;
  return {
    xOf: (minutes) => centreX + scale * (map.project([minutes / 60, centre.lat]).x - centreX),
    yOf: (minutes) =>
      centreY + scale * (map.project([centre.lng, minutes / 60]).y - centreY) - geometry.top,
    lonMinutes: (step) => ticksInRange(west - step / 60, east, step),
    latMinutes: (step) => ticksInRange(south - step / 60, north, step),
    minorMin,
    majorMin,
  };
}

function drawLongitudeBand(
  context: CanvasRenderingContext2D,
  axes: Axes,
  interior: Box,
  geometry: EngravingGeometry,
): void {
  const upper = geometry.side === "upper";
  const chequerTop = upper ? geometry.frame - CHEQUER_PX : geometry.height - geometry.frame;
  for (const minutes of axes.lonMinutes(axes.minorMin)) {
    const start = Math.max(interior.left, axes.xOf(minutes));
    const end = Math.min(interior.right, axes.xOf(minutes + axes.minorMin));
    if (end <= start) continue;
    context.fillStyle = chequerParity(minutes, axes.minorMin)
      ? GATE_LIVERY.frameInk
      : GATE_LIVERY.frameChequerPaper;
    context.fillRect(start, chequerTop, end - start, CHEQUER_PX);
  }
  context.beginPath();
  for (const y of [crisp(chequerTop) - 1, crisp(chequerTop + CHEQUER_PX)]) {
    context.moveTo(interior.left - 1, y);
    context.lineTo(interior.right + 1, y);
  }
  context.strokeStyle = GATE_LIVERY.frameInk;
  context.lineWidth = 1;
  context.stroke();

  const labelZone = geometry.frame - CHEQUER_PX;
  const labelMiddle = upper ? labelZone / 2 : geometry.height - labelZone / 2;
  context.textBaseline = "middle";
  for (const minutes of axes.lonMinutes(axes.majorMin)) {
    const x = axes.xOf(minutes);
    if (x < interior.left + LABEL_EDGE_GAP_PX || x > interior.right - LABEL_EDGE_GAP_PX * 2)
      continue;
    const label = tickLabel(minutes);
    context.fillStyle = GATE_LIVERY.frameInk;
    context.fillRect(Math.round(x), upper ? 2 : geometry.height - labelZone, 1, labelZone - 2);
    context.fillStyle = label.degree ? GATE_LIVERY.ink : GATE_LIVERY.frameLabel;
    context.fillText(label.text, Math.round(x) + 3, labelMiddle + 0.5);
  }
}

function drawLatitudeBand(
  context: CanvasRenderingContext2D,
  axes: Axes,
  interior: Box,
  geometry: EngravingGeometry,
  edge: "left" | "right",
): void {
  const chequerLeft = edge === "left" ? geometry.frame - CHEQUER_PX : interior.right;
  for (const minutes of axes.latMinutes(axes.minorMin)) {
    const a = axes.yOf(minutes);
    const b = axes.yOf(minutes + axes.minorMin);
    const start = Math.max(interior.top, Math.min(a, b));
    const end = Math.min(interior.bottom, Math.max(a, b));
    if (end <= start) continue;
    context.fillStyle = chequerParity(minutes, axes.minorMin)
      ? GATE_LIVERY.frameInk
      : GATE_LIVERY.frameChequerPaper;
    context.fillRect(chequerLeft, start, CHEQUER_PX, end - start);
  }
  context.beginPath();
  for (const x of [crisp(chequerLeft) - 1, crisp(chequerLeft + CHEQUER_PX)]) {
    context.moveTo(x, interior.top);
    context.lineTo(x, interior.bottom);
  }
  context.strokeStyle = GATE_LIVERY.frameInk;
  context.lineWidth = 1;
  context.stroke();

  const labelZone = geometry.frame - CHEQUER_PX;
  const zoneLeft = edge === "left" ? 0 : interior.right + CHEQUER_PX;
  context.textBaseline = "middle";
  for (const minutes of axes.latMinutes(axes.majorMin)) {
    const y = axes.yOf(minutes);
    if (y < interior.top + LABEL_EDGE_GAP_PX * 2 || y > interior.bottom - LABEL_EDGE_GAP_PX)
      continue;
    const label = tickLabel(minutes);
    context.fillStyle = GATE_LIVERY.frameInk;
    context.fillRect(edge === "left" ? 2 : zoneLeft, Math.round(y), labelZone - 2, 1);
    context.save();
    context.translate(zoneLeft + labelZone / 2 + 0.5, Math.round(y) - 3);
    context.rotate(-Math.PI / 2);
    context.fillStyle = label.degree ? GATE_LIVERY.ink : GATE_LIVERY.frameLabel;
    context.fillText(label.text, 0, 0);
    context.restore();
  }
}

export function drawGraticule(
  context: CanvasRenderingContext2D,
  map: MapLibreMap,
  geometry: EngravingGeometry,
): void {
  context.clearRect(0, 0, geometry.width, geometry.height);
  const interior = interiorOf(geometry);
  if (!isNorthUp(map) || interior.right <= interior.left || interior.bottom <= interior.top) return;
  const axes = axesFor(map, geometry, 1);
  context.save();
  context.beginPath();
  context.rect(
    interior.left,
    interior.top,
    interior.right - interior.left,
    interior.bottom - interior.top,
  );
  context.clip();
  context.beginPath();
  for (const minutes of axes.lonMinutes(axes.majorMin)) {
    const x = crisp(axes.xOf(minutes));
    context.moveTo(x, interior.top);
    context.lineTo(x, interior.bottom);
  }
  for (const minutes of axes.latMinutes(axes.majorMin)) {
    const y = crisp(axes.yOf(minutes));
    context.moveTo(interior.left, y);
    context.lineTo(interior.right, y);
  }
  context.strokeStyle = GATE_LIVERY.engraving;
  context.lineWidth = 1;
  context.stroke();
  context.restore();
}

export function drawNeatline(
  context: CanvasRenderingContext2D,
  map: MapLibreMap,
  geometry: EngravingGeometry,
  mapScale: number,
): void {
  context.clearRect(0, 0, geometry.width, geometry.height);
  const interior = interiorOf(geometry);
  if (!isNorthUp(map) || geometry.frame < CHEQUER_PX * 2 || interior.right <= interior.left) return;
  const axes = axesFor(map, geometry, mapScale);
  context.font = `500 ${LABEL_FONT_PX}px ${geometry.fontFamily}`;
  drawLongitudeBand(context, axes, interior, geometry);
  drawLatitudeBand(context, axes, interior, geometry, "left");
  drawLatitudeBand(context, axes, interior, geometry, "right");
}
