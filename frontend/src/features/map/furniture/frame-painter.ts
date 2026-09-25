import {
  formatTickLabel,
  isWholeDegree,
  type TickSpec,
  tickDegrees,
  tickIndexRange,
} from "./ticks";
import type { ViewportProjector } from "./viewport-projector";

export type FrameColors = { ink: string; paper: string; label: string };

export const DAY_LIVERY_FRAME_COLORS: FrameColors = {
  ink: "rgba(17,20,22,.70)",
  paper: "#FFFFFF",
  label: "#5C6569",
};

const TICK_BAND_MAX_PX = 8;
const LABEL_GAP_PX = 3;
const LABEL_EDGE_CLEARANCE_PX = 2;
const TICK_FONT_SIZE_PX = 10.5;
const TICK_CAP_HEIGHT_PX = 7.4;

type Axis = "lng" | "lat";
type Side = "top" | "bottom" | "left" | "right";
type Rect = [x: number, y: number, width: number, height: number];

const SIDES: readonly Side[] = ["top", "bottom", "left", "right"];
const SIDE_AXIS: Readonly<Record<Side, Axis>> = {
  top: "lng",
  bottom: "lng",
  left: "lat",
  right: "lat",
};

type Extent = { west: number; east: number; south: number; north: number };

export type FramePaintInput = {
  projector: ViewportProjector;
  band: number;
  ticks: TickSpec;
  colors: FrameColors;
  fontFamily: string;
};

type Layout = { width: number; height: number; band: number; chequer: number; strip: number };

type SideContext = FramePaintInput & {
  layout: Layout;
  range: [from: number, to: number];
  position: (degrees: number) => number;
  span: [start: number, end: number];
};

function chequerDepth(band: number): number {
  return band >= 16 ? 4 : 3;
}

function layoutFor(width: number, height: number, band: number): Layout {
  const chequer = chequerDepth(band);
  return { width, height, band, chequer, strip: band - 1 - chequer };
}

function paintBand(
  ctx: CanvasRenderingContext2D,
  { width, height, band }: Layout,
  colors: FrameColors,
): void {
  ctx.fillStyle = colors.paper;
  ctx.beginPath();
  ctx.rect(0, 0, width, height);
  ctx.rect(band, band, width - band * 2, height - band * 2);
  ctx.fill("evenodd");
  ctx.strokeStyle = colors.ink;
  ctx.lineWidth = 1;
  ctx.strokeRect(band - 0.5, band - 0.5, width - band * 2 + 1, height - band * 2 + 1);
}

function chequerCell(
  side: Side,
  start: number,
  end: number,
  { width, height, band, chequer, strip }: Layout,
): Rect {
  if (side === "top") return [start, strip, end - start, chequer];
  if (side === "bottom") return [start, height - band + 1, end - start, chequer];
  if (side === "left") return [strip, start, chequer, end - start];
  return [width - band + 1, start, chequer, end - start];
}

function paintChequer(ctx: CanvasRenderingContext2D, side: Side, context: SideContext): void {
  const { ticks, colors, layout, range, position, span } = context;
  const [first, last] = tickIndexRange(range[0], range[1], ticks.minorMinutes);
  ctx.fillStyle = colors.ink;
  for (let index = first - 1; index <= last; index += 1) {
    if (Math.abs(index % 2) !== 1) continue;
    const a = position(tickDegrees(index, ticks.minorMinutes));
    const b = position(tickDegrees(index + 1, ticks.minorMinutes));
    const start = Math.round(Math.max(span[0], Math.min(a, b)));
    const end = Math.round(Math.min(span[1], Math.max(a, b)));
    if (end > start) ctx.fillRect(...chequerCell(side, start, end, layout));
  }
}

function paintChequerOutline(
  ctx: CanvasRenderingContext2D,
  { width, height, chequer, strip }: Layout,
  colors: FrameColors,
): void {
  ctx.strokeStyle = colors.ink;
  ctx.lineWidth = 1;
  ctx.strokeRect(strip - 0.5, strip - 0.5, width - strip * 2 + 1, height - strip * 2 + 1);
  const corner = chequer + 1;
  const far = { x: width - strip - corner, y: height - strip - corner };
  ctx.fillStyle = colors.ink;
  ctx.fillRect(strip, strip, corner, corner);
  ctx.fillRect(far.x, strip, corner, corner);
  ctx.fillRect(strip, far.y, corner, corner);
  ctx.fillRect(far.x, far.y, corner, corner);
}

function labelZone(side: Side, { width, height, strip }: Layout): { near: number; far: number } {
  if (side === "top" || side === "left") return { near: 1, far: strip - 1 };
  const edge = side === "bottom" ? height : width;
  return { near: edge - strip + 1, far: edge - 1 };
}

function majorIndices(context: SideContext, axis: Axis): number[] {
  const [first, last] = tickIndexRange(
    context.range[0],
    context.range[1],
    context.ticks.majorMinutes,
  );
  const indices = Array.from(
    { length: Math.max(0, last - first + 1) },
    (_, offset) => first + offset,
  );
  return axis === "lat" ? indices.reverse() : indices;
}

function paintMajorTicks(ctx: CanvasRenderingContext2D, side: Side, context: SideContext): void {
  const { ticks, colors, layout, position, span, fontFamily } = context;
  const axis = SIDE_AXIS[side];
  const zone = labelZone(side, layout);
  const baseline = zone.near + (zone.far - zone.near + TICK_CAP_HEIGHT_PX) / 2;
  ctx.font = `500 ${TICK_FONT_SIZE_PX}px ${fontFamily}`;
  ctx.textBaseline = "alphabetic";
  ctx.textAlign = "left";
  let labelled = 0;
  for (const index of majorIndices(context, axis)) {
    const degrees = tickDegrees(index, ticks.majorMinutes);
    const at = Math.round(position(degrees));
    if (at < span[0] + LABEL_EDGE_CLEARANCE_PX || at > span[1] - LABEL_EDGE_CLEARANCE_PX) continue;
    const text = formatTickLabel(degrees, labelled === 0);
    const textWidth = ctx.measureText(text).width;
    const labelInk = isWholeDegree(degrees) ? colors.ink : colors.label;
    ctx.fillStyle = colors.ink;
    if (axis === "lng") {
      ctx.fillRect(at, zone.near, 1, zone.far - zone.near);
      if (at + LABEL_GAP_PX + textWidth > span[1] - LABEL_EDGE_CLEARANCE_PX) continue;
      ctx.fillStyle = labelInk;
      ctx.fillText(text, at + LABEL_GAP_PX + 1, baseline);
    } else {
      ctx.fillRect(zone.near, at, zone.far - zone.near, 1);
      if (at - LABEL_GAP_PX - textWidth < span[0] + LABEL_EDGE_CLEARANCE_PX) continue;
      ctx.save();
      ctx.translate(baseline, at - LABEL_GAP_PX);
      ctx.rotate(-Math.PI / 2);
      ctx.fillStyle = labelInk;
      ctx.fillText(text, 0, 0);
      ctx.restore();
    }
    labelled += 1;
  }
}

function paintTicksOnly(ctx: CanvasRenderingContext2D, side: Side, context: SideContext): void {
  const { ticks, colors, layout, range, position, span } = context;
  const { width, height, band } = layout;
  const [first, last] = tickIndexRange(range[0], range[1], ticks.minorMinutes);
  const perMajor = Math.round(ticks.majorMinutes / ticks.minorMinutes);
  ctx.fillStyle = colors.ink;
  for (let index = first; index <= last; index += 1) {
    const at = Math.round(position(tickDegrees(index, ticks.minorMinutes)));
    if (at < span[0] || at > span[1]) continue;
    const length = index % perMajor === 0 ? band - 2 : Math.ceil(band / 2) - 1;
    if (side === "top") ctx.fillRect(at, band - 1 - length, 1, length);
    else if (side === "bottom") ctx.fillRect(at, height - band + 1, 1, length);
    else if (side === "left") ctx.fillRect(band - 1 - length, at, length, 1);
    else ctx.fillRect(width - band + 1, at, length, 1);
  }
}

function viewExtent({ width, height, unproject }: ViewportProjector, band: number): Extent {
  return {
    west: unproject(band, height / 2).lng,
    east: unproject(width - band, height / 2).lng,
    north: unproject(width / 2, band).lat,
    south: unproject(width / 2, height - band).lat,
  };
}

export function paintFrame(ctx: CanvasRenderingContext2D, input: FramePaintInput): void {
  const { projector, band, colors } = input;
  const { width, height } = projector;
  ctx.clearRect(0, 0, width, height);
  if (band <= 0 || width <= band * 2 || height <= band * 2) return;

  const layout = layoutFor(width, height, band);
  const extent = viewExtent(projector, band);
  const middle = { lng: (extent.west + extent.east) / 2, lat: (extent.south + extent.north) / 2 };
  const contextFor = (side: Side): SideContext => {
    const isLng = SIDE_AXIS[side] === "lng";
    return {
      ...input,
      layout,
      range: isLng ? [extent.west, extent.east] : [extent.south, extent.north],
      position: isLng
        ? (degrees) => projector.project(degrees, middle.lat).x
        : (degrees) => projector.project(middle.lng, degrees).y,
      span: isLng ? [band, width - band] : [band, height - band],
    };
  };

  paintBand(ctx, layout, colors);
  if (band <= TICK_BAND_MAX_PX) {
    for (const side of SIDES) paintTicksOnly(ctx, side, contextFor(side));
    return;
  }
  ctx.strokeStyle = colors.ink;
  ctx.lineWidth = 1;
  ctx.strokeRect(0.5, 0.5, width - 1, height - 1);
  for (const side of SIDES) paintChequer(ctx, side, contextFor(side));
  paintChequerOutline(ctx, layout, colors);
  for (const side of SIDES) paintMajorTicks(ctx, side, contextFor(side));
}
