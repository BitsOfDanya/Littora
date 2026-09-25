export type PluralForms = readonly [one: string, few: string, many: string];

export function pluralRu(count: number, [one, few, many]: PluralForms): string {
  const lastTwo = Math.abs(count) % 100;
  const last = lastTwo % 10;
  if (lastTwo >= 11 && lastTwo <= 14) return many;
  if (last === 1) return one;
  if (last >= 2 && last <= 4) return few;
  return many;
}

export function countRu(count: number, forms: PluralForms): string {
  return `${count} ${pluralRu(count, forms)}`;
}
