"use client";

import { useMemo } from "react";
import type { JournalFixtureRow } from "@/data/monitor-dossier";
import { useSurveyPlanEntry } from "@/features/monitor/survey-plan-store";
import { useCandidateEvents } from "@/features/shell/queue/use-queue";
import { shortDay } from "@/features/time-rail/rail-tracks";
import { formatUtcTime } from "@/lib/format/time";
import { DemoTag } from "@/ui/demo-mark";
import { CollapsibleSection } from "./collapsible-section";

type JournalRow = JournalFixtureRow & { key: string; demo: boolean };

const EVENT_ACTOR: Record<string, string> = {
  beaching_risk: "прогноз",
  new_detection: "модель",
  growth: "модель",
};

export function JournalSection({
  candidateId,
  fixture,
  open,
  onToggle,
  isDemo,
}: {
  candidateId: string;
  fixture: readonly JournalFixtureRow[];
  open: boolean;
  onToggle: (open: boolean) => void;
  isDemo: boolean;
}) {
  const events = useCandidateEvents(candidateId);
  const plan = useSurveyPlanEntry(candidateId);

  const rows = useMemo(() => {
    const entries: JournalRow[] = [
      ...fixture.map((row, index) => ({ ...row, key: `fixture-${index}`, demo: isDemo })),
      ...events.map((event) => ({
        key: `event-${event.id}`,
        at: event.occurredAt,
        actor: EVENT_ACTOR[event.kind] ?? "система",
        text: `Событие: ${event.title}`,
        demo: event.isDemo,
      })),
      ...events.flatMap((event) =>
        event.acknowledgement
          ? [
              {
                key: `ack-${event.id}`,
                at: event.acknowledgement.at,
                actor: event.acknowledgement.actor,
                text: `Квитировано: ${event.title}`,
                demo: event.isDemo,
              },
            ]
          : [],
      ),
      ...(plan
        ? [
            {
              key: "plan",
              at: plan.addedAt,
              actor: plan.actor,
              text: "Добавлено в план обследования",
              demo: isDemo,
            },
          ]
        : []),
    ];
    return entries.sort((a, b) => b.at.localeCompare(a.at));
  }, [fixture, events, plan, isDemo]);

  return (
    <CollapsibleSection
      id="dossier-journal"
      index="07"
      title="Журнал"
      open={open}
      onToggle={onToggle}
      aside={<span className="font-mono text-[11px] text-text-tertiary">{rows.length}</span>}
    >
      <ol className="flex flex-col">
        {rows.map((row) => (
          <li
            key={row.key}
            className="grid grid-cols-[82px_minmax(0,1fr)_auto] items-start gap-x-2 border-b border-line-hairline py-1.5 last:border-b-0"
          >
            <span className="font-mono text-[11px] leading-4 text-text-secondary">
              {shortDay(row.at)} {formatUtcTime(row.at)}
            </span>
            <span className="text-[12px] leading-4 text-text-primary">
              {row.text}
              <span className="text-text-tertiary"> · {row.actor}</span>
            </span>
            {row.demo ? <DemoTag /> : <span />}
          </li>
        ))}
      </ol>
    </CollapsibleSection>
  );
}
