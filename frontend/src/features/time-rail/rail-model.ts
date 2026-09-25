export type Placed<T> = { item: T; ratio: number; offsetPx: number };

export function spreadMarks<T>(
  items: readonly T[],
  ratioOf: (item: T) => number,
  widthPx: number,
  stepPx: number,
): Placed<T>[] {
  const sorted = [...items].sort((a, b) => ratioOf(a) - ratioOf(b));
  const placed: Placed<T>[] = [];
  let lastX = -Infinity;
  for (const item of sorted) {
    const ratio = ratioOf(item);
    const x = ratio * widthPx;
    const drawnX = Math.max(x, lastX + stepPx);
    placed.push({ item, ratio, offsetPx: drawnX - x });
    lastX = drawnX;
  }
  return placed;
}

export function nearestIndex<T>(
  items: readonly T[],
  from: number,
  accept: (item: T) => boolean,
): number {
  let best = -1;
  for (let distance = 1; distance < items.length; distance += 1) {
    for (const index of [from - distance, from + distance]) {
      if (index >= 0 && index < items.length && accept(items[index])) {
        best = index;
        break;
      }
    }
    if (best !== -1) break;
  }
  return best;
}

export function ageLabel(fromIso: string, now: number): string {
  const hours = Math.max(0, Math.floor((now - Date.parse(fromIso)) / 3_600_000));
  if (hours < 24) return `${hours} ч назад`;
  const days = Math.floor(hours / 24);
  const rest = hours % 24;
  return rest && days < 3 ? `${days} сут ${rest} ч назад` : `${days} сут назад`;
}
