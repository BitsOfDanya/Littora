const SUBSCRIPT_DIGITS = "₀₁₂₃₄₅₆₇₈₉";

export function shortCandidateId(id: string): string {
  const serial = /-(\d{3,})$/.exec(id)?.[1];
  return serial ? `LT-${serial}` : id;
}

export function soundingText(coverage: number): string {
  const tenths = Math.max(0, Math.round(coverage * 1000));
  return `${Math.floor(tenths / 10)}${SUBSCRIPT_DIGITS[tenths % 10]}`;
}

export function candidateLabel(id: string, coverage: number): string {
  return `${shortCandidateId(id)} ${soundingText(coverage)}`;
}

export function labelParts(id: string, coverage: number): { main: string; sub: string } {
  const tenths = Math.max(0, Math.round(coverage * 1000));
  return { main: `${shortCandidateId(id)} ${Math.floor(tenths / 10)}`, sub: String(tenths % 10) };
}
