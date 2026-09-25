export function rowNormalise(counts: readonly (readonly number[])[]): number[][] {
  return counts.map((row) => {
    const total = row.reduce((sum, value) => sum + value, 0);
    return row.map((value) => (total > 0 ? value / total : 0));
  });
}

export function inkOpacity(share: number): number {
  const clamped = Math.min(1, Math.max(0, share));
  return clamped <= 0 ? 0 : 0.06 + 0.84 * Math.sqrt(clamped);
}

export function prefersInverseText(share: number): boolean {
  return inkOpacity(share) >= 0.56;
}
