"use client";

import { useMutation, useMutationState, useQuery, useQueryClient } from "@tanstack/react-query";
import { DEMO_SURVEY_PLAN } from "@/demo/survey";
import type { Sourced } from "@/domain/data-origin";
import type { LngLat } from "@/domain/geo";
import type { SentinelPlatform } from "@/domain/scene";
import type { SurveyScoreComponent } from "@/domain/survey";
import { getAnalysis } from "@/lib/api/analyses";
import { ApiError, describeApiError } from "@/lib/api/errors";
import {
  createSurvey,
  getSurvey,
  type SurveyOptions,
  type SurveyResponse,
  type SurveyResultStatus,
  type SurveyTargetItem,
} from "@/lib/api/survey";
import { getMeta } from "@/lib/api/system";
import { queryKeys } from "@/lib/query/query-keys";
import { useAnalysisStore } from "@/state/analysis-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { useDriftState } from "./forecast";
import { useDemoSourced } from "./use-sourced";

export type SurveyMethod = "vessel" | "uav" | "tasking";

export type SurveyPort = { name: string; position: LngLat; berth: LngLat };

export type SurveyDrift = { bearingDeg: number; kmPerDay: number };

export type SurveySearchRadius = { baseKm: number; kmPerDay: number };

export type SurveyScoreWeights = Readonly<Record<SurveyScoreComponent, number>>;

export type SurveyComponents = Readonly<Partial<Record<SurveyScoreComponent, number>>>;

export type SurveyTrack = {
  path: readonly LngLat[];
  radii: readonly { hour: number; km: number }[];
};

export type SurveyUrgencyLevel = "high" | "medium" | "low" | "unknown";

export type SurveyTargetDetails = {
  zoneIds: readonly string[];
  areaKm2: number;
  pixels: number;
  probabilityMax: number;
  probabilityMean: number;
  why: readonly string[];
  checks: readonly string[];
  urgency: {
    level: SurveyUrgencyLevel;
    label: string;
    leaves1kmH: number | null;
    leaves2kmH: number | null;
    beaching: { name: string; probability: number; windowH: readonly [number, number] } | null;
  };
  window: { from: string; to: string; basis: string } | null;
  windowNote: string | null;
  spotUntil: string | null;
  nearestPort: { name: string; distanceKm: number } | null;
  shoreKm: number | null;
  uav: { feasible: boolean | null; rangeKm: number; basis: string };
  visit: number | null;
  eta: string | null;
  shiftAtEtaKm: number | null;
};

export type SurveyPlanTarget = {
  id: string;
  candidateId: string;
  observedAt: string;
  observedPosition: LngLat;
  components: SurveyComponents;
  reason: string;
  drift: SurveyDrift;
  searchRadius: SurveySearchRadius;
  method: SurveyMethod;
  track?: SurveyTrack;
  details?: SurveyTargetDetails;
};

export type SurveyRouteStop =
  { kind: "via"; position: LngLat } | { kind: "target"; targetId: string };

export type PlannedPass = {
  id: string;
  platform: SentinelPlatform;
  relativeOrbit: number;
  acquiredAt: string;
  swath: { westLng: number; eastLng: number };
};

export type SurveyExitWindow = {
  from: string;
  to: string;
  daylight: readonly [string, string];
  beachingAt: string | null;
  scenarioEnd: string | null;
  relaxed: "beaching" | "scenario_end" | "daylight" | null;
  basis: string;
  past: boolean;
};

export type SurveyPlanMeta = {
  analysisId: string;
  label: string;
  reason: string;
  t0: string;
  readyAt: string;
  drift: { used: boolean; note: string };
  zones: { total: number; groups: number; planned: number };
  exitWindow: SurveyExitWindow | null;
  port: { name: string; nameEn: string; source: string; distanceKm: number | null } | null;
  route: { distanceKm: number; durationH: number; method: string } | null;
  options: { speedKn: number; uavRangeKm: number; routeTargets: number };
  scoring: Readonly<Record<string, string>>;
  passesNote: string | null;
  messages: readonly string[];
};

export type SurveyPlan = {
  id: string;
  aoiId: string;
  issuedAt: string;
  port: SurveyPort | null;
  departure: { defaultDate: string; timeUtc: string; utcOffsetH: number };
  window: { from: string; to: string };
  speedKn: number;
  dwellMin: number;
  weights: SurveyScoreWeights;
  route: readonly SurveyRouteStop[];
  track?: readonly LngLat[];
  targets: readonly SurveyPlanTarget[];
  passes: readonly PlannedPass[];
  meta?: SurveyPlanMeta;
};

export type SurveyResult = {
  analysisId: string;
  status: SurveyResultStatus;
  label: string;
  reason: string;
  plan: SurveyPlan | null;
};

export type SurveyState =
  | { status: "demo" }
  | { status: "planned" }
  | { status: "no-analysis" }
  | { status: "loading" }
  | { status: "no-zones"; reason: string | null }
  | { status: "absent"; build: (options?: SurveyOptions) => void; driftReady: boolean }
  | { status: "building" }
  | { status: "failed"; message: string; retry: () => void }
  | { status: "unavailable"; label: string; reason: string; retry: () => void }
  | {
      status: "ready";
      plan: SurveyPlan;
      rebuild: (options?: SurveyOptions) => void;
      driftReady: boolean;
      busy: boolean;
    };

export type SurveyInputs = {
  live: boolean;
  capable: boolean;
  analysisId: string | null;
  analysis: { zones: number | null; error: unknown };
  survey: { result: SurveyResult | null | undefined; error: unknown };
  build: { status: "idle" | "pending" | "success" | "error"; error: unknown } | null;
  driftReady: boolean;
};

export type SurveyActions = {
  build: (options?: SurveyOptions) => void;
  reloadAnalysis: () => void;
  reloadSurvey: () => void;
};

export const SURVEY_DEMO_SOURCE = "demo/survey";

const PLATFORMS: readonly SentinelPlatform[] = ["S2A", "S2B", "S2C"];
const META_STALE_MS = 5 * 60_000;
const BUILD_KEY = ["survey", "build"] as const;

const isPlatform = (value: string): value is SentinelPlatform =>
  PLATFORMS.some((platform) => platform === value);

function toComponents(components: SurveyTargetItem["components"]): SurveyComponents {
  const entries = Object.entries(components).filter(
    (entry): entry is [SurveyScoreComponent, number] => entry[1] !== null,
  );
  return Object.fromEntries(entries);
}

function toDetails(item: SurveyTargetItem): SurveyTargetDetails {
  const beaching = item.urgency.beaching;
  return {
    zoneIds: item.zone_ids,
    areaKm2: item.area_km2,
    pixels: item.pixels,
    probabilityMax: item.probability_max,
    probabilityMean: item.probability_mean,
    why: item.why,
    checks: item.checks,
    urgency: {
      level: item.urgency.level,
      label: item.urgency.label,
      leaves1kmH: item.urgency.leaves_1km_h,
      leaves2kmH: item.urgency.leaves_2km_h,
      beaching: beaching
        ? { name: beaching.name, probability: beaching.probability, windowH: beaching.window_h }
        : null,
    },
    window: item.window,
    windowNote: item.window_note,
    spotUntil: item.spot_until,
    nearestPort: item.nearest_port
      ? { name: item.nearest_port.name, distanceKm: item.nearest_port.distance_km }
      : null,
    shoreKm: item.shore_km,
    uav: { feasible: item.uav.feasible, rangeKm: item.uav.range_km, basis: item.uav.basis },
    visit: item.visit,
    eta: item.eta,
    shiftAtEtaKm: item.shift_at_eta_km,
  };
}

export function toSurveyTarget(item: SurveyTargetItem): SurveyPlanTarget {
  return {
    id: item.id,
    candidateId: item.lead_zone,
    observedAt: item.observed_at,
    observedPosition: item.position,
    components: toComponents(item.components),
    reason: item.reason,
    drift: {
      bearingDeg: item.drift?.bearing_deg ?? 0,
      kmPerDay: item.drift?.km_per_day ?? 0,
    },
    searchRadius: { baseKm: item.search_radius.base_km, kmPerDay: item.search_radius.km_per_day },
    method: item.method,
    ...(item.drift ? { track: { path: item.drift.track, radii: item.drift.radii } } : {}),
    details: toDetails(item),
  };
}

function toPasses(response: SurveyResponse): PlannedPass[] {
  return response.passes.flatMap((pass) =>
    isPlatform(pass.platform)
      ? [
          {
            id: pass.id,
            platform: pass.platform,
            relativeOrbit: pass.relative_orbit ?? 0,
            acquiredAt: pass.acquired_at,
            swath: { westLng: pass.swath[0], eastLng: pass.swath[1] },
          },
        ]
      : [],
  );
}

export function toSurveyPlan(response: SurveyResponse, aoiId: string): SurveyPlan | null {
  const { t0, ready_at: readyAt } = response;
  if (response.status.status !== "estimate" || !t0 || !readyAt || !response.targets.length)
    return null;
  const exit = response.exit_window;
  const departure = exit?.departure ?? readyAt;
  const port = response.port;
  const anchor = port?.position ?? response.targets[0].position;
  const route: SurveyRouteStop[] = response.route
    ? [
        ...response.route.order.map((targetId) => ({ kind: "target" as const, targetId })),
        ...(port ? [{ kind: "via" as const, position: port.position }] : []),
      ]
    : [];
  return {
    id: `PLAN-${response.analysis_id}`,
    aoiId,
    issuedAt: readyAt,
    port: port ? { name: port.name, position: port.position, berth: port.position } : null,
    departure: {
      defaultDate: departure.slice(0, 10),
      timeUtc: departure.slice(11, 16),
      utcOffsetH: Math.round(anchor[0] / 15),
    },
    window: {
      from: (exit?.from ?? departure).slice(0, 10),
      to: (exit?.to ?? departure).slice(0, 10),
    },
    speedKn: response.request.speed_kn,
    dwellMin: response.request.dwell_min,
    weights: response.weights,
    route,
    track: (response.route?.track ?? []).map(([lng, lat]) => [lng, lat] as LngLat),
    targets: response.targets.map(toSurveyTarget),
    passes: toPasses(response),
    meta: {
      analysisId: response.analysis_id,
      label: response.status.label,
      reason: response.reason,
      t0,
      readyAt,
      drift: { used: response.drift.used, note: response.drift.note },
      zones: {
        total: response.zones.total,
        groups: response.zones.groups,
        planned: response.zones.planned,
      },
      exitWindow: exit
        ? {
            from: exit.from,
            to: exit.to,
            daylight: exit.daylight,
            beachingAt: exit.beaching_at,
            scenarioEnd: exit.scenario_end,
            relaxed: exit.relaxed,
            basis: exit.basis,
            past: exit.past,
          }
        : null,
      port: port
        ? {
            name: port.name,
            nameEn: port.name_en,
            source: port.source,
            distanceKm: port.distance_km,
          }
        : null,
      route: response.route
        ? {
            distanceKm: response.route.distance_km,
            durationH: response.route.duration_h,
            method: response.route.method,
          }
        : null,
      options: {
        speedKn: response.request.speed_kn,
        uavRangeKm: response.request.uav_range_km,
        routeTargets: response.request.route_targets,
      },
      scoring: response.scoring,
      passesNote: response.passes_note,
      messages: response.messages,
    },
  };
}

export function toSurveyResult(response: SurveyResponse, aoiId: string): SurveyResult {
  return {
    analysisId: response.analysis_id,
    status: response.status.status,
    label: response.status.label,
    reason: response.reason,
    plan: toSurveyPlan(response, aoiId),
  };
}

export function countPlannableZones(
  zones: readonly { geometry?: unknown; centroid?: unknown }[],
): number {
  return zones.filter((zone) => Boolean(zone.geometry)).length;
}

export function surveyStateOf(input: SurveyInputs, actions: SurveyActions): SurveyState {
  if (!input.live) return { status: "demo" };
  if (!input.capable) return { status: "planned" };
  if (!input.analysisId) return { status: "no-analysis" };
  if (input.analysis.error)
    return {
      status: "failed",
      message: `Анализ не загружен: ${describeApiError(input.analysis.error)}`,
      retry: actions.reloadAnalysis,
    };
  if (input.analysis.zones === null) return { status: "loading" };
  if (input.analysis.zones === 0) return { status: "no-zones", reason: null };
  const { result } = input.survey;
  const pending = input.build?.status === "pending";
  if (result?.status === "estimate" && result.plan)
    return {
      status: "ready",
      plan: result.plan,
      rebuild: actions.build,
      driftReady: input.driftReady,
      busy: pending,
    };
  if (pending) return { status: "building" };
  if (result?.status === "no_zones" || result?.status === "estimate")
    return { status: "no-zones", reason: result.reason };
  if (input.build?.status === "error")
    return {
      status: "failed",
      message: describeApiError(input.build.error),
      retry: () => actions.build(),
    };
  if (result?.status === "insufficient_data")
    return {
      status: "unavailable",
      label: result.label,
      reason: result.reason,
      retry: () => actions.build(),
    };
  if (input.survey.error)
    return {
      status: "failed",
      message: describeApiError(input.survey.error),
      retry: actions.reloadSurvey,
    };
  if (result === undefined) return { status: "loading" };
  return { status: "absent", build: actions.build, driftReady: input.driftReady };
}

async function loadSurvey(
  analysisId: string,
  aoiId: string,
  signal: AbortSignal,
): Promise<SurveyResult | null> {
  try {
    return toSurveyResult(await getSurvey(analysisId, signal), aoiId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

function useSurveyCapable(): boolean {
  const meta = useQuery({
    queryKey: queryKeys.system.meta,
    queryFn: ({ signal }) => getMeta(signal),
    staleTime: META_STALE_MS,
  });
  return (
    meta.data?.capabilities.some(
      (capability) => capability.key === "survey_planning" && capability.status === "available",
    ) ?? false
  );
}

type BuildVariables = { analysisId: string; aoiId: string; options: SurveyOptions };

function useBuildSurvey() {
  const client = useQueryClient();
  return useMutation({
    mutationKey: BUILD_KEY,
    mutationFn: ({ analysisId, aoiId, options }: BuildVariables) =>
      createSurvey(analysisId, options).then((response) => toSurveyResult(response, aoiId)),
    onSuccess: (result, { analysisId }) =>
      client.setQueryData(queryKeys.analyses.survey(analysisId), result),
  }).mutate;
}

function useLatestBuild(analysisId: string | null): SurveyInputs["build"] {
  const runs = useMutationState({
    filters: { mutationKey: BUILD_KEY },
    select: (mutation) => ({
      analysisId: (mutation.state.variables as BuildVariables | undefined)?.analysisId,
      status: mutation.state.status,
      error: mutation.state.error,
    }),
  });
  for (let index = runs.length - 1; index >= 0; index -= 1)
    if (runs[index].analysisId === analysisId) return runs[index];
  return null;
}

export type SurveySource = { state: SurveyState; plan: Sourced<SurveyPlan> };

export function useSurveySource(): SurveySource {
  const demo = useDemoSourced<SurveyPlan>(DEMO_SURVEY_PLAN);
  const live = demo.origin !== "demo";
  const capable = useSurveyCapable();
  const analysisId = useAnalysisStore((state) => state.analysisId);
  const aoiId = useWorkspaceStore((state) => state.aoiId);
  const active = live && capable && analysisId !== null;
  const analysis = useQuery({
    queryKey: queryKeys.analyses.detail(analysisId ?? ""),
    queryFn: ({ signal }) => getAnalysis(analysisId ?? "", signal),
    enabled: active,
    staleTime: Infinity,
    select: (data) => countPlannableZones(data.detection.zones),
  });
  const zones = active ? (analysis.data ?? null) : null;
  const survey = useQuery({
    queryKey: queryKeys.analyses.survey(analysisId ?? ""),
    queryFn: ({ signal }) => loadSurvey(analysisId ?? "", aoiId, signal),
    enabled: active && (zones ?? 0) > 0,
    staleTime: 0,
    refetchOnWindowFocus: false,
  });
  const drift = useDriftState();
  const build = useBuildSurvey();
  const latest = useLatestBuild(analysisId);
  const state = surveyStateOf(
    {
      live,
      capable,
      analysisId,
      analysis: { zones, error: analysis.error },
      survey: { result: survey.data, error: survey.error },
      build: latest,
      driftReady: drift.status === "ready",
    },
    {
      build: (options = {}) => {
        if (analysisId) build({ analysisId, aoiId, options });
      },
      reloadAnalysis: () => void analysis.refetch(),
      reloadSurvey: () => void survey.refetch(),
    },
  );
  if (demo.origin === "demo") return { state, plan: demo };
  if (state.status === "ready") return { state, plan: { origin: "api", data: state.plan } };
  return { state, plan: demo.origin === "none" ? demo : { origin: "none", demo: "not-provided" } };
}

export const useSurveyPlan = (): Sourced<SurveyPlan> => useSurveySource().plan;
