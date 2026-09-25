import type { DebrisCandidate, SurveyPriority } from "@/domain/detection";

const PRIORITY_RANK: Record<SurveyPriority, number> = { high: 0, medium: 1, low: 2 };

export function orderByPriority(candidates: readonly DebrisCandidate[]): DebrisCandidate[] {
  return [...candidates].sort(
    (a, b) =>
      PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority] ||
      b.confidence.score - a.confidence.score,
  );
}

export function stepInOrder(
  ordered: readonly DebrisCandidate[],
  currentId: string | null,
  delta: 1 | -1,
  accept: (candidate: DebrisCandidate) => boolean = () => true,
): DebrisCandidate | undefined {
  const count = ordered.length;
  const start = ordered.findIndex((candidate) => candidate.id === currentId);
  for (let step = 1; step <= count; step += 1) {
    const raw = start === -1 ? (delta > 0 ? step - 1 : count - step) : start + delta * step;
    const candidate = ordered[((raw % count) + count) % count];
    if (accept(candidate)) return candidate;
  }
  return undefined;
}
