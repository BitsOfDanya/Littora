const DAY_MS = 86_400_000;

export type TimeWindow = { start: number; end: number };

export function windowAround(timestamps: readonly number[], paddingDays = 3): TimeWindow {
  const start = Math.min(...timestamps) - paddingDays * DAY_MS;
  const end = Math.max(...timestamps) + paddingDays * DAY_MS;
  return { start, end };
}

export function toRatio(window: TimeWindow, timestamp: number): number {
  return (timestamp - window.start) / (window.end - window.start);
}

export function monthTicks(
  window: TimeWindow,
): { timestamp: number; month: number; year: number }[] {
  const ticks: { timestamp: number; month: number; year: number }[] = [];
  const cursor = new Date(window.start);
  cursor.setUTCDate(1);
  cursor.setUTCHours(0, 0, 0, 0);
  while (cursor.getTime() <= window.end) {
    if (cursor.getTime() >= window.start) {
      ticks.push({
        timestamp: cursor.getTime(),
        month: cursor.getUTCMonth(),
        year: cursor.getUTCFullYear(),
      });
    }
    cursor.setUTCMonth(cursor.getUTCMonth() + 1);
  }
  return ticks;
}

export function dayTicks(window: TimeWindow, everyDays: number): number[] {
  const ticks: number[] = [];
  const first = Math.ceil(window.start / DAY_MS) * DAY_MS;
  for (let timestamp = first; timestamp <= window.end; timestamp += DAY_MS * everyDays)
    ticks.push(timestamp);
  return ticks;
}

export const DAY = DAY_MS;

export const MIN_WINDOW_DAYS = 6;

export function zoomWindow(window: TimeWindow, anchor: number, factor: number): TimeWindow {
  const span = window.end - window.start;
  const nextSpan = Math.max(MIN_WINDOW_DAYS * DAY_MS, span * factor);
  const ratio = span > 0 ? (anchor - window.start) / span : 0.5;
  const start = anchor - nextSpan * ratio;
  return { start, end: start + nextSpan };
}

export function panWindow(window: TimeWindow, deltaRatio: number): TimeWindow {
  const shift = (window.end - window.start) * deltaRatio;
  return { start: window.start + shift, end: window.end + shift };
}

export function clampWindow(window: TimeWindow, bounds: TimeWindow): TimeWindow {
  const span = Math.min(window.end - window.start, bounds.end - bounds.start);
  const start = Math.min(Math.max(window.start, bounds.start), bounds.end - span);
  return { start, end: start + span };
}

export function isSameWindow(a: TimeWindow, b: TimeWindow): boolean {
  return Math.abs(a.start - b.start) < 1000 && Math.abs(a.end - b.end) < 1000;
}

export function fromRatio(window: TimeWindow, ratio: number): number {
  return window.start + ratio * (window.end - window.start);
}
