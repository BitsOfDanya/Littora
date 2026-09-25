"use client";

import { useMemo } from "react";
import type { DebrisCandidate } from "@/domain/detection";
import { formatNumber } from "@/lib/format/numbers";
import { pluralRu } from "./plural";
import { useInViewCount } from "./use-in-view-count";

const NNBSP = " ";

export function ObjectsSummary({ candidates }: { candidates: readonly DebrisCandidate[] }) {
  const centroids = useMemo(() => candidates.map((candidate) => candidate.centroid), [candidates]);
  const inView = useInViewCount(centroids);
  const areaKm2 = candidates.reduce((sum, candidate) => sum + candidate.areaM2, 0) / 1_000_000;
  const count = candidates.length;

  return (
    <span className="font-mono text-[11px] text-text-secondary">
      {count} {pluralRu(count, ["кандидат", "кандидата", "кандидатов"])} ·{" "}
      {formatNumber(areaKm2, 2)}
      {NNBSP}км² · в кадре {inView ?? "—"}
    </span>
  );
}
