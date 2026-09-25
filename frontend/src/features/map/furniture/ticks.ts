import { formatNumber } from "@/lib/format/numbers";

const WORLD_TILE_PX = 512;
const MINUTES_PER_TURN = 360 * 60;
const WHOLE_STEPS_MINUTES = [1, 2, 5, 10, 15, 30, 60, 120, 300] as const;
const ALL_STEPS_MINUTES = [0.1, 0.2, 0.5, ...WHOLE_STEPS_MINUTES] as const;
const SUBMINUTE_FROM_PX = 60;
const TENTHS = 10;

export const MIN_MINOR_SPACING_PX = 7;
export const MIN_MAJOR_SPACING_PX = 70;

export type TickSpec = { minorMinutes: number; majorMinutes: number };

export function pixelsPerLongitudeMinute(zoom: number): number {
  return (WORLD_TILE_PX * 2 ** zoom) / MINUTES_PER_TURN;
}

function isMultipleOf(value: number, step: number): boolean {
  return Math.round(value * TENTHS) % Math.round(step * TENTHS) === 0;
}

export function tickSpecFor(zoom: number): TickSpec {
  const spacing = pixelsPerLongitudeMinute(zoom);
  const steps: readonly number[] =
    spacing >= SUBMINUTE_FROM_PX ? ALL_STEPS_MINUTES : WHOLE_STEPS_MINUTES;
  const coarsest = steps[steps.length - 1];
  const minorMinutes = steps.find((step) => step * spacing >= MIN_MINOR_SPACING_PX) ?? coarsest;
  const majorMinutes =
    steps.find(
      (step) =>
        step >= minorMinutes &&
        isMultipleOf(step, minorMinutes) &&
        step * spacing >= MIN_MAJOR_SPACING_PX,
    ) ?? coarsest;
  return { minorMinutes, majorMinutes };
}

export function tickIndexRange(
  fromDeg: number,
  toDeg: number,
  stepMinutes: number,
): [first: number, last: number] {
  const low = Math.min(fromDeg, toDeg) * 60;
  const high = Math.max(fromDeg, toDeg) * 60;
  return [Math.ceil(low / stepMinutes - 1e-9), Math.floor(high / stepMinutes + 1e-9)];
}

export function tickDegrees(index: number, stepMinutes: number): number {
  return (index * stepMinutes) / 60;
}

function splitDegrees(degrees: number): { whole: number; minutes: number } {
  const absolute = Math.abs(degrees);
  const totalTenths = Math.round(absolute * 60 * TENTHS);
  const whole = Math.floor(totalTenths / (60 * TENTHS));
  return { whole, minutes: (totalTenths - whole * 60 * TENTHS) / TENTHS };
}

function formatMinutes(minutes: number): string {
  const digits = Number.isInteger(minutes) ? 0 : 1;
  return `${formatNumber(minutes, digits).padStart(digits ? 4 : 2, "0")}′`;
}

export function isWholeDegree(degrees: number): boolean {
  return splitDegrees(degrees).minutes === 0;
}

export function formatTickLabel(degrees: number, withDegrees: boolean): string {
  const { whole, minutes } = splitDegrees(degrees);
  if (minutes === 0) return `${whole}°`;
  return withDegrees ? `${whole}°${formatMinutes(minutes)}` : formatMinutes(minutes);
}
