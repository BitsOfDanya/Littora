export const WAVE_VIEW_WIDTH = 1000;

function seededRandom(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state * 16807) % 2147483647;
    return state / 2147483647;
  };
}

function wavePoints(
  baseY: number,
  amplitude: number,
  seed: number,
  step: number,
): Array<[number, number]> {
  const random = seededRandom(seed);
  const points: Array<[number, number]> = [];
  for (let x = -step; x <= WAVE_VIEW_WIDTH + step; x += step)
    points.push([x, baseY + (random() - 0.5) * 2 * amplitude]);
  return points;
}

export function wavePath(baseY: number, amplitude: number, seed: number, step = 125): string {
  const points = wavePoints(baseY, amplitude, seed, step);
  let path = `M${points[0][0]},${points[0][1].toFixed(2)}`;
  for (let index = 1; index < points.length - 1; index += 1) {
    const [x, y] = points[index];
    const [nextX, nextY] = points[index + 1];
    path += ` Q${x},${y.toFixed(2)} ${(x + nextX) / 2},${((y + nextY) / 2).toFixed(2)}`;
  }
  const [lastX, lastY] = points[points.length - 1];
  return `${path} L${lastX},${lastY.toFixed(2)}`;
}

export function areaAbove(wave: string): string {
  return `${wave} L${WAVE_VIEW_WIDTH + 250},-1 L-250,-1 Z`;
}

export function areaBelow(wave: string, bottom: number): string {
  return `${wave} L${WAVE_VIEW_WIDTH + 250},${bottom + 1} L-250,${bottom + 1} Z`;
}
