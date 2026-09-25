"use client";

import { useHotkey } from "@/features/shell/hotkeys";
import { useAcknowledgeCandidate, useCandidateEvents } from "@/features/shell/queue/use-queue";
import { formatUtcTime } from "@/lib/format/time";
import { useShellUiStore } from "@/state/shell-ui-store";
import { Button } from "@/ui/button";
import { cn } from "@/ui/cn";
import { IconCheck } from "@/ui/icons";
import { Kbd } from "@/ui/kbd";

function latestAcknowledgement(events: ReturnType<typeof useCandidateEvents>): string | null {
  const stamps = events.flatMap((event) =>
    event.acknowledgement ? [event.acknowledgement.at] : [],
  );
  return stamps.sort().at(-1) ?? null;
}

export function AcknowledgeButton({
  candidateId,
  className,
}: {
  candidateId: string;
  className?: string;
}) {
  const events = useCandidateEvents(candidateId);
  const acknowledge = useAcknowledgeCandidate();
  const modalOpen = useShellUiStore((state) => state.shortcutSheetOpen);
  const canAcknowledge = events.some((event) => event.state === "new");
  const acknowledgedAt = latestAcknowledgement(events);

  useHotkey("KeyA", () => acknowledge(candidateId), { enabled: canAcknowledge && !modalOpen });

  if (!canAcknowledge) {
    return (
      <Button
        size="lg"
        className={cn("flex-1", className)}
        disabled
        title="Новых событий по объекту нет"
      >
        {acknowledgedAt ? `Квитировано ${formatUtcTime(acknowledgedAt)}` : "Событий нет"}
      </Button>
    );
  }
  return (
    <Button
      variant="primary"
      size="lg"
      className={cn("flex-1", className)}
      aria-keyshortcuts="A"
      title="Квитировать новые события объекта · A"
      onClick={() => acknowledge(candidateId)}
    >
      <IconCheck size={14} />
      Квитировать
      <Kbd className="border-primary-text/50 text-primary-text">A</Kbd>
    </Button>
  );
}
