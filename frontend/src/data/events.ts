"use client";

import { DEMO_EVENTS } from "@/demo/events";
import { useDemoSourced } from "./use-sourced";

export type EventSeverity = "alarm" | "caution" | "info";

export type EventKind =
  "beaching_risk" | "new_detection" | "growth" | "cloudy_scene" | "api_lost" | "api_restored";

export type EventStamp = "time" | "date";

export type QueueEvent = {
  id: string;
  kind: EventKind;
  severity: EventSeverity;
  occurredAt: string;
  stamp: EventStamp;
  title: string;
  candidateId: string | null;
  acknowledged: { at: string; actor: string } | null;
};

export const EVENT_PRIORITY: Record<EventSeverity, 1 | 2 | 3> = { alarm: 1, caution: 2, info: 3 };

export const useQueueEventFixtures = () => useDemoSourced(DEMO_EVENTS);
