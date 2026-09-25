"use client";

import type { DebrisCandidate } from "@/domain/detection";
import { type QueueRow, useCandidateEvents } from "@/features/shell/queue/use-queue";
import { formatDistance } from "@/lib/format/numbers";
import { formatUtcTime } from "@/lib/format/time";
import { SeverityGlyph, type Severity } from "@/ui/indicators";
import { StatusTag, type StatusTone } from "@/ui/status-tag";
import { REVIEW_STATUS_LABEL } from "../labels";
import { CopyButton } from "./copy-button";

const SEVERITY_RANK: Record<Severity, number> = { alarm: 0, caution: 1, info: 2 };
const TRIAGE_WORD: Record<Severity, string> = {
  alarm: "ТРЕВОГА · П1",
  caution: "ВНИМАНИЕ · П2",
  info: "СВЕДЕНИЯ · П3",
};
const TRIAGE_TONE: Record<Severity, string> = {
  alarm: "text-state-alarm",
  caution: "text-state-caution",
  info: "text-state-info",
};
const STATUS_TONE: Partial<Record<DebrisCandidate["status"], StatusTone>> = {
  confirmed_litter: "selection",
  natural: "ok",
};

export function candidateTitle(candidate: DebrisCandidate): string {
  const kind = candidate.shape === "windrow" ? "Скопление-нить" : "Пятно";
  return `${kind} · ${formatDistance(candidate.lengthM)}`;
}

function worstSeverity(rows: readonly QueueRow[]): Severity | null {
  return rows.reduce<Severity | null>(
    (worst, row) =>
      worst === null || SEVERITY_RANK[row.severity] < SEVERITY_RANK[worst] ? row.severity : worst,
    null,
  );
}

function TriageLine({ rows }: { rows: readonly QueueRow[] }) {
  const severity = worstSeverity(rows);
  if (!severity)
    return <p className="text-[12px] leading-4 text-text-tertiary">Событий в очереди нет</p>;
  const pending = rows.some((row) => row.state === "new");
  const lastAck = rows
    .flatMap((row) => (row.acknowledgement ? [row.acknowledgement] : []))
    .sort((a, b) => a.at.localeCompare(b.at))
    .at(-1);
  return (
    <p className="flex flex-wrap items-center gap-x-1.5 text-[12px] leading-4">
      <SeverityGlyph severity={severity} acknowledged={!pending} size={14} />
      <span
        className={`font-mono text-[11px] font-medium tracking-[0.06em] ${TRIAGE_TONE[severity]}`}
      >
        {TRIAGE_WORD[severity]}
      </span>
      <span className="text-text-secondary">
        ·{" "}
        {pending
          ? "не квитировано"
          : lastAck
            ? `квитировано ${formatUtcTime(lastAck.at)} · ${lastAck.actor}`
            : "сведения"}
      </span>
    </p>
  );
}

export function DossierHeader({ candidate }: { candidate: DebrisCandidate }) {
  const rows = useCandidateEvents(candidate.id);
  return (
    <>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <h2 className="font-mono text-[17px] leading-[22px] font-semibold text-text-primary">
          {candidate.id}
        </h2>
        <CopyButton value={candidate.id} label="Скопировать идентификатор" />
        <StatusTag tone={STATUS_TONE[candidate.status] ?? "neutral"} className="ml-auto">
          {REVIEW_STATUS_LABEL[candidate.status]}
        </StatusTag>
      </div>
      <p className="text-[15px] leading-5 font-semibold text-text-primary">
        {candidateTitle(candidate)}
      </p>
      <TriageLine rows={rows} />
    </>
  );
}
