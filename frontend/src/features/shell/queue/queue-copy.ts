import type { EventSeverity } from "@/data/events";
import { formatUtcTime } from "@/lib/format/time";
import { countRu } from "../orientation/plural";
import type { QueueRow, QueueRowState } from "./use-queue";

export const STATE_WORD: Record<QueueRowState, string> = {
  new: "НОВОЕ",
  acknowledged: "КВИТ.",
  info: "СВЕД.",
};

export const SEVERITY_LABEL: Record<EventSeverity, string> = {
  alarm: "Тревога · П1",
  caution: "Внимание · П2",
  info: "Сведения · П3",
};

export const SEVERITY_BAR: Record<EventSeverity, string> = {
  alarm: "bg-state-alarm",
  caution: "bg-state-caution",
  info: "bg-state-info",
};

export function eventStamp(row: Pick<QueueRow, "occurredAt" | "stamp">): string {
  if (row.stamp === "time") return formatUtcTime(row.occurredAt);
  return `${row.occurredAt.slice(8, 10)}.${row.occurredAt.slice(5, 7)}`;
}

export function newEventsPhrase(count: number): string {
  return countRu(count, ["новое событие", "новых события", "новых событий"]);
}

export function acknowledgementLine(row: QueueRow): string | null {
  if (!row.acknowledgement) return null;
  return `Квитировано ${formatUtcTime(row.acknowledgement.at)} · ${row.acknowledgement.actor}`;
}

export function rowAccessibleName(row: QueueRow): string {
  const parts = [SEVERITY_LABEL[row.severity], eventStamp(row), row.title, STATE_WORD[row.state]];
  const ack = acknowledgementLine(row);
  if (ack) parts.push(ack);
  if (row.isDemo) parts.push("ДЕМО, фикстура интерфейса");
  return parts.join(" · ");
}
