export type Rgba = [number, number, number, number];

export function hexToRgba(hex: string, alpha = 255): Rgba {
  const value = hex.replace("#", "");
  return [
    Number.parseInt(value.slice(0, 2), 16),
    Number.parseInt(value.slice(2, 4), 16),
    Number.parseInt(value.slice(4, 6), 16),
    alpha,
  ];
}

const RGBA_FUNCTION =
  /^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)$/i;

export function cssColorToRgba(color: string, alpha?: number): Rgba {
  const match = RGBA_FUNCTION.exec(color.trim());
  if (!match) return hexToRgba(color, alpha === undefined ? 255 : Math.round(alpha * 255));
  const [, red, green, blue, ownAlpha] = match;
  const resolvedAlpha = alpha ?? (ownAlpha === undefined ? 1 : Number(ownAlpha));
  return [Number(red), Number(green), Number(blue), Math.round(resolvedAlpha * 255)];
}

export function withAlpha([red, green, blue]: Rgba, alpha: number): Rgba {
  return [red, green, blue, Math.round(alpha * 255)];
}

export type StepRamp = { stops: readonly number[]; colors: readonly string[] };

export function colorForValue(ramp: StepRamp, value: number): string {
  let index = 0;
  while (index < ramp.stops.length - 1 && value >= ramp.stops[index + 1]) index += 1;
  return ramp.colors[index];
}

export function isBelowRamp(ramp: StepRamp, value: number): boolean {
  return value < ramp.stops[0];
}
