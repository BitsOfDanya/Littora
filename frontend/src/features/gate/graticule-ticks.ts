export const TICK_INTERVALS_MIN = [1, 2, 5, 10, 15, 30, 60, 120, 300] as const;

const MIN_MINOR_PX = 7;
const MIN_MAJOR_PX = 70;
const WIDEST_INTERVAL_MIN = 300;

export type TickPlan = { minorMin: number; majorMin: number };

export type TickLabel = { text: string; degree: boolean };

export function planTicks(pxPerMinute: number): TickPlan {
  const minorMin =
    TICK_INTERVALS_MIN.find((minutes) => minutes * pxPerMinute >= MIN_MINOR_PX) ??
    WIDEST_INTERVAL_MIN;
  const majorMin =
    TICK_INTERVALS_MIN.find(
      (minutes) => minutes % minorMin === 0 && minutes * pxPerMinute >= MIN_MAJOR_PX,
    ) ?? WIDEST_INTERVAL_MIN;
  return { minorMin, majorMin };
}

export function ticksInRange(fromDeg: number, toDeg: number, stepMin: number): number[] {
  const low = Math.min(fromDeg, toDeg) * 60;
  const high = Math.max(fromDeg, toDeg) * 60;
  const ticks: number[] = [];
  for (let minutes = Math.ceil(low / stepMin) * stepMin; minutes <= high; minutes += stepMin)
    ticks.push(minutes);
  return ticks;
}

export function chequerParity(minutes: number, stepMin: number): 0 | 1 {
  return (((Math.round(minutes / stepMin) % 2) + 2) % 2) as 0 | 1;
}

export function tickLabel(minutes: number): TickLabel {
  const total = Math.round(Math.abs(minutes));
  const degrees = Math.floor(total / 60);
  const rest = total - degrees * 60;
  if (rest === 0) return { text: `${degrees}°`, degree: true };
  return { text: `${String(rest).padStart(2, "0")}′`, degree: false };
}
