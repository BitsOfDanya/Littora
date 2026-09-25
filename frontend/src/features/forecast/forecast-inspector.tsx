"use client";

import Link from "next/link";
import { useCallback, useMemo } from "react";
import { findAoi } from "@/config/aois";
import { WORKSPACE_MODES } from "@/config/modes";
import type { BeachSegmentRisk } from "@/data/forecast";
import { fitAoi, fitTo } from "@/features/map/camera";
import { useMainMap } from "@/features/map/use-main-map";
import type { Crumb } from "@/features/inspector/parts/breadcrumbs";
import { InspectorFrame } from "@/features/inspector/parts/inspector-frame";
import { JumpNav, type JumpTarget } from "@/features/inspector/parts/jump-nav";
import { DemoAction } from "@/features/cartouche/planned-group-note";
import { modeHref, useViewQuery } from "@/features/shell/orientation/modes";
import { ShellSlot } from "@/features/shell/shell-slots";
import { useApiMeta } from "@/features/system/use-capabilities";
import { formatUtcDateTime } from "@/lib/format/time";
import { useWorkspaceStore } from "@/state/workspace-store";
import { Button, buttonClasses } from "@/ui/button";
import { IconArrowRight, IconDownload } from "@/ui/icons";
import { PlannedState, PlannedTag } from "@/ui/planned";
import { boundsOf } from "./drift-math";
import { chooseHorizon } from "./forecast-hotkeys";
import { horizonRow, RAIL_T0_ID } from "./forecast-model";
import { HorizonSeg } from "./horizon-seg";
import {
  BeachingSection,
  ConditionsSection,
  HorizonsSection,
  PositionSection,
  SECTION_IDS,
  SourceSection,
} from "./inspector-sections";
import { type SelectedForecast, useSelectedForecast } from "./use-selected-forecast";

const SURVEY_MODE = WORKSPACE_MODES[3];

const JUMP_TARGETS: readonly JumpTarget[] = [
  { id: SECTION_IDS.position, label: "Положение" },
  { id: SECTION_IDS.horizons, label: "Горизонты" },
  { id: SECTION_IDS.beaching, label: "Берег" },
  { id: SECTION_IDS.source, label: "Источник" },
  { id: SECTION_IDS.conditions, label: "Условия" },
];

function scrollableAncestor(element: HTMLElement | null): HTMLElement | null {
  for (let node = element?.parentElement ?? null; node; node = node.parentElement) {
    const overflow = getComputedStyle(node).overflowY;
    if ((overflow === "auto" || overflow === "scroll") && node.scrollHeight > node.clientHeight)
      return node;
  }
  return null;
}

function shortDate(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
}

function useCrumbs(leaf: string, t0: string | null, onLeaf: () => void): Crumb[] {
  const map = useMainMap();
  const aoi = findAoi(useWorkspaceStore((state) => state.aoiId));
  return useMemo(
    () => [
      {
        label: aoi?.name ?? "Район",
        serif: true,
        onSelect: map && aoi ? () => fitAoi(map, aoi) : undefined,
      },
      {
        label: t0 ? `от снимка ${shortDate(t0)}` : "снимок не выбран",
        onSelect: t0 ? () => document.getElementById(RAIL_T0_ID)?.focus() : undefined,
      },
      { label: leaf, onSelect: onLeaf },
    ],
    [aoi, map, t0, leaf, onLeaf],
  );
}

function ReadyInspector({
  selected,
}: {
  selected: Extract<SelectedForecast, { status: "ready" }>;
}) {
  const { candidate, forecast, run, isDemo } = selected;
  const map = useMainMap();
  const horizonH = useWorkspaceStore((state) => state.forecastHorizonH);
  const clearSelection = useWorkspaceStore((state) => state.clearSelection);
  const viewQuery = useViewQuery();
  const scrollTop = useCallback(() => {
    scrollableAncestor(document.getElementById(SECTION_IDS.position))?.scrollTo({ top: 0 });
  }, []);
  const crumbs = useCrumbs(candidate.id, run.t0, scrollTop);
  const row = horizonRow(forecast, horizonH);

  const focusRisk = useCallback(
    (risk: BeachSegmentRisk) => {
      if (map && risk.path.length > 1)
        fitTo(map, boundsOf(risk.path), { maxZoom: 12.5, durationMs: 400 });
    },
    [map],
  );

  if (!row) return null;

  return (
    <InspectorFrame
      label={`Прогноз дрейфа ${candidate.id}`}
      eyebrow="Прогноз дрейфа"
      crumbs={crumbs}
      demoSource={isDemo ? "demo/forecast" : null}
      onClose={clearSelection}
      selectionRule
      header={
        <>
          <h2 className="font-mono text-[17px] leading-[22px] font-semibold text-text-primary">
            {candidate.id}
          </h2>
          <p className="text-[12px] leading-4 text-text-secondary">
            от снимка T₀ <span className="font-mono">{formatUtcDateTime(run.t0)}</span> · прогон{" "}
            <span className="font-mono">{formatUtcDateTime(run.runAt)}</span> · ансамбль{" "}
            {run.ensembleSize}
          </p>
          <HorizonSeg value={horizonH} onChange={chooseHorizon} className="pt-1" />
        </>
      }
      nav={<JumpNav targets={JUMP_TARGETS} />}
      footer={
        <>
          <Link href={modeHref(SURVEY_MODE, viewQuery)} className={buttonClasses("primary", "lg")}>
            Спланировать выход
            <IconArrowRight size={14} />
          </Link>
          <Button
            size="lg"
            disabled
            icon={<IconDownload size={14} />}
            title="Экспорт GeoJSON появится с возможностью drift_forecast"
          >
            GeoJSON
          </Button>
          <PlannedTag capability="drift_forecast" className="self-center" />
        </>
      }
    >
      <PositionSection forecast={forecast} run={run} row={row} isDemo={isDemo} />
      <HorizonsSection forecast={forecast} horizonH={horizonH} onChoose={chooseHorizon} />
      <BeachingSection forecast={forecast} run={run} onFocus={focusRisk} />
      <SourceSection forecast={forecast} />
      <ConditionsSection run={run} isDemo={isDemo} />
    </InspectorFrame>
  );
}

function PlannedInspector({ candidateId }: { candidateId: string }) {
  const meta = useApiMeta();
  const clearSelection = useWorkspaceStore((state) => state.clearSelection);
  const crumbs = useCrumbs(candidateId, null, () => undefined);
  const status = meta.isPending ? "loading" : meta.isError ? "error" : "planned";
  return (
    <InspectorFrame
      label={`Прогноз дрейфа ${candidateId}`}
      eyebrow="Прогноз дрейфа"
      crumbs={crumbs}
      onClose={clearSelection}
      selectionRule
      header={
        <h2 className="font-mono text-[17px] leading-[22px] font-semibold text-text-primary">
          {candidateId}
        </h2>
      }
    >
      <div className="p-4">
        <PlannedState
          title="Прогноз дрейфа — не подключено"
          capability="drift_forecast"
          status={status}
          requirement="поля течений CMEMS, ветер GFS и выбранное пятно."
          action={
            status === "error" ? (
              <Button onClick={() => void meta.refetch()}>Повторить</Button>
            ) : (
              <DemoAction />
            )
          }
        >
          Частицы течений, облака вероятности на +6…+72{" "}ч и обратный дрейф к вероятному
          источнику.
        </PlannedState>
      </div>
    </InspectorFrame>
  );
}

function MissingInspector({ candidateId }: { candidateId: string }) {
  const clearSelection = useWorkspaceStore((state) => state.clearSelection);
  const crumbs = useCrumbs(candidateId, null, () => undefined);
  return (
    <InspectorFrame
      label={`Прогноз дрейфа ${candidateId}`}
      eyebrow="Прогноз дрейфа"
      crumbs={crumbs}
      onClose={clearSelection}
      selectionRule
      header={
        <h2 className="font-mono text-[17px] leading-[22px] font-semibold text-text-primary">
          {candidateId}
        </h2>
      }
    >
      <p className="p-4 text-[13px] text-text-secondary">
        Для этого пятна прогноз ещё не рассчитан. Выберите другое пятно или вернитесь позже.
      </p>
    </InspectorFrame>
  );
}

export function ForecastInspector() {
  const selected = useSelectedForecast();
  if (selected.status === "idle") return null;
  return (
    <ShellSlot region="inspector">
      {selected.status === "ready" ? (
        <ReadyInspector selected={selected} />
      ) : selected.status === "planned" ? (
        <PlannedInspector candidateId={selected.candidateId} />
      ) : (
        <MissingInspector candidateId={selected.candidateId} />
      )}
    </ShellSlot>
  );
}
