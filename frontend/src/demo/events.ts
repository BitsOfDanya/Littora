import type { QueueEvent } from "@/data/events";
import type { DebrisCandidate } from "@/domain/detection";
import { formatArea, formatNumber, formatPercent, formatSignedPercent } from "@/lib/format/numbers";
import { DEMO_CANDIDATES } from "./candidates";
import { DEMO_FORECASTS } from "./forecast";
import { DEMO_LATEST_SCENE, DEMO_SCENES } from "./scenes";

const LATEST_DAY = DEMO_LATEST_SCENE.acquiredAt.slice(0, 10);
const OPERATOR_ACK = { at: `${LATEST_DAY}T18:52:00Z`, actor: "оператор" } as const;
const FALLBACK_BEACHING = { segment: "Омоа", probability: 0.62 } as const;
const CLOUDY_THRESHOLD = 0.6;

function shortDate(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
}

function beachingEvent(): QueueEvent {
  const forecast = DEMO_FORECASTS.find((entry) => entry.beachingRisk) ?? DEMO_FORECASTS[0];
  const risk = forecast?.beachingRisk ?? FALLBACK_BEACHING;
  return {
    id: `EV-${LATEST_DAY}-beaching`,
    kind: "beaching_risk",
    severity: "alarm",
    occurredAt: `${LATEST_DAY}T18:40:00Z`,
    stamp: "time",
    title: `Риск выноса на берег: ${risk.segment} · до +72 ч (${formatNumber(risk.probability, 2)})`,
    candidateId: forecast?.candidateId ?? DEMO_CANDIDATES[0].id,
    acknowledged: null,
  };
}

function newestDetection(): DebrisCandidate {
  const fresh = DEMO_CANDIDATES.filter(
    (candidate) => candidate.change === null && candidate.persistence.detectedIn === 1,
  );
  return fresh.find((candidate) => candidate.priority !== "low") ?? fresh[0] ?? DEMO_CANDIDATES[0];
}

function newDetectionEvent(): QueueEvent {
  const candidate = newestDetection();
  return {
    id: `EV-${candidate.id}-new`,
    kind: "new_detection",
    severity: "caution",
    occurredAt: candidate.observedAt,
    stamp: "date",
    title: `Новое скопление ${formatArea(candidate.areaM2)}, покрытие ${formatPercent(candidate.coverage.value)}`,
    candidateId: candidate.id,
    acknowledged: null,
  };
}

function growthEvent(): QueueEvent | null {
  const growing = DEMO_CANDIDATES.filter(
    (candidate) => (candidate.change?.areaDeltaRatio ?? 0) > 0,
  ).sort((a, b) => (b.change?.areaDeltaRatio ?? 0) - (a.change?.areaDeltaRatio ?? 0))[0];
  if (!growing?.change) return null;
  return {
    id: `EV-${growing.id}-growth`,
    kind: "growth",
    severity: "caution",
    occurredAt: growing.observedAt,
    stamp: "date",
    title: `Рост площади ${formatSignedPercent(growing.change.areaDeltaRatio)} к ${shortDate(growing.change.previousObservedAt)}`,
    candidateId: growing.id,
    acknowledged: OPERATOR_ACK,
  };
}

function cloudySceneEvent(): QueueEvent | null {
  const scene = [...DEMO_SCENES].reverse().find((entry) => entry.cloudCover >= CLOUDY_THRESHOLD);
  if (!scene) return null;
  return {
    id: `EV-${scene.acquiredAt.slice(0, 10)}-cloudy`,
    kind: "cloudy_scene",
    severity: "info",
    occurredAt: scene.acquiredAt,
    stamp: "date",
    title: `Снимок ${shortDate(scene.acquiredAt)}: облачность ${formatPercent(scene.cloudCover)}, пригодно ${formatPercent(scene.validWaterFraction)} воды`,
    candidateId: null,
    acknowledged: null,
  };
}

export const DEMO_EVENTS: readonly QueueEvent[] = [
  beachingEvent(),
  newDetectionEvent(),
  growthEvent(),
  cloudySceneEvent(),
].filter((event): event is QueueEvent => event !== null);
