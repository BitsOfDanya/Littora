"use client";

import Link from "next/link";
import { useMemo } from "react";
import { findAoi } from "@/config/aois";
import { WORKSPACE_MODES } from "@/config/modes";
import { TIMELINE_DEMO_SOURCE } from "@/data/timeline";
import type { Crumb } from "@/features/inspector/parts/breadcrumbs";
import { InspectorFrame } from "@/features/inspector/parts/inspector-frame";
import { fitAoi } from "@/features/map/camera";
import { useIsPhoneWidth } from "@/features/map/furniture/use-frame-width";
import { useMainMap } from "@/features/map/use-main-map";
import { modeHref, useViewQuery } from "@/features/shell/orientation/modes";
import { ShellSlot } from "@/features/shell/shell-slots";
import { useApiMeta } from "@/features/system/use-capabilities";
import { formatDistance } from "@/lib/format/numbers";
import { useWorkspaceStore } from "@/state/workspace-store";
import { Button, buttonClasses } from "@/ui/button";
import { IconArrowRight, IconSwap } from "@/ui/icons";
import { Kbd } from "@/ui/kbd";
import { PlannedState } from "@/ui/planned";
import { intervalText } from "./compare-format";
import { COMPARE_HONESTY_NOTE, useCompareHonestyNote } from "./compare-method-box";
import { dayMonth, intervalOf, MOSAIC_YEARS, objectRows, sideTotals } from "./compare-model";
import { ObjectDynamicsBody } from "./compare-object";
import { ComparePickers, MosaicPair } from "./compare-pickers";
import { AreaSummary, ObjectDeltas } from "./compare-summary";
import { LiveChange, LivePassList, LiveState, LiveSummary } from "./live-sections";
import { RAIL_B_PASS_ID } from "./compare-tracks";
import { useCompareActions, useCompareData } from "./use-compare";

const FORECAST_MODE = WORKSPACE_MODES[2];

function useRootCrumb(): Crumb {
  const map = useMainMap();
  const aoiId = useWorkspaceStore((state) => state.aoiId);
  const aoi = findAoi(aoiId);
  return {
    label: aoi?.name ?? "Район",
    serif: true,
    onSelect: map && aoi ? () => fitAoi(map, aoi) : undefined,
  };
}

function focusRailPass(): void {
  document.getElementById(RAIL_B_PASS_ID)?.focus();
}

function scrollInspectorTop(): void {
  let element = document.getElementById("timeline-inspector-top")?.parentElement ?? null;
  while (element) {
    const overflow = getComputedStyle(element).overflowY;
    if (overflow === "auto" || overflow === "scroll") {
      element.scrollTo({ top: 0 });
      return;
    }
    element = element.parentElement;
  }
}

function HonestyNote() {
  const phone = useIsPhoneWidth();
  const note = useCompareHonestyNote();
  if (!phone) return null;
  return <p className="text-[12px] leading-4 text-text-tertiary">{note}</p>;
}

function Footer({ onSwap, canSwap }: { onSwap: () => void; canSwap: boolean }) {
  const query = useViewQuery();
  return (
    <>
      <Button
        size="lg"
        disabled={!canSwap}
        onClick={onSwap}
        icon={<IconSwap />}
        title="Поменять A и B · X"
      >
        Поменять A и B<Kbd>X</Kbd>
      </Button>
      <Link
        href={modeHref(FORECAST_MODE, query)}
        className={buttonClasses("default", "lg")}
        title="Прогноз дрейфа · 3"
      >
        Прогноз дрейфа
        <IconArrowRight />
      </Link>
    </>
  );
}

function PlannedPanel() {
  const root = useRootCrumb();
  const meta = useApiMeta();
  const demoFixtures = useWorkspaceStore((state) => state.demoFixtures);
  const setDemoFixtures = useWorkspaceStore((state) => state.setDemoFixtures);
  const status = meta.isPending ? "loading" : meta.isError ? "error" : "planned";
  return (
    <InspectorFrame
      label="Сравнение A/B"
      eyebrow="Сравнение A/B"
      crumbs={[root, { label: `мозаики ${MOSAIC_YEARS.a} → ${MOSAIC_YEARS.b}` }]}
      header={
        <>
          <MosaicPair />
          <p className="text-[12px] leading-4 text-text-secondary">{COMPARE_HONESTY_NOTE}</p>
        </>
      }
    >
      <div className="p-4">
        <PlannedState
          title="Сравнение по датам — не подключено"
          capability="change_tracking"
          status={status}
          requirement="детекция по обеим датам."
          action={
            status === "error" ? (
              <Button onClick={() => void meta.refetch()}>Повторить</Button>
            ) : demoFixtures ? (
              <p className="text-[12px] text-text-tertiary">Для этого района демо-данных нет.</p>
            ) : (
              <Button onClick={() => setDemoFixtures(true)} title="Включить демо-фикстуры · D">
                Показать на демо-данных
              </Button>
            )
          }
        >
          Здесь будут два снимка A и B, итог изменений по району и по каждому объекту, слой Δ.
        </PlannedState>
      </div>
    </InspectorFrame>
  );
}

function ComparePanel() {
  const root = useRootCrumb();
  const { scenes, histories, candidates, pair, isDemo, live, passes } = useCompareData();
  const actions = useCompareActions(scenes, pair);
  const selectedId = useWorkspaceStore((state) => state.selectedCandidateId);
  const selectCandidate = useWorkspaceStore((state) => state.selectCandidate);
  const rows = useMemo(
    () => (pair ? objectRows(candidates, histories, pair) : []),
    [candidates, histories, pair],
  );
  if (!pair) return <PlannedPanel />;

  const selected = candidates.find((candidate) => candidate.id === selectedId);
  const history = histories.find((entry) => entry.candidateId === selected?.id);
  const pairCrumb: Crumb = {
    label: `A ${dayMonth(pair.a.acquiredAt)} → B ${dayMonth(pair.b.acquiredAt)}`,
    onSelect: selected ? () => selectCandidate(null) : focusRailPass,
  };
  const leaf: Crumb = { label: selected ? selected.id : "Итог", onSelect: scrollInspectorTop };

  return (
    <InspectorFrame
      label={selected ? `Динамика пятна ${selected.id}` : "Сравнение A/B"}
      eyebrow={selected ? "Динамика пятна" : "Сравнение A/B"}
      crumbs={[root, pairCrumb, leaf]}
      demoSource={isDemo ? TIMELINE_DEMO_SOURCE : null}
      onClose={selected ? () => selectCandidate(null) : undefined}
      selectionRule={Boolean(selected)}
      header={
        <>
          <span id="timeline-inspector-top" className="sr-only" />
          {selected ? (
            <p className="flex items-baseline gap-2">
              <span className="font-mono text-[17px] font-semibold text-accent-selection">
                {selected.id}
              </span>
              <span className="text-[12px] text-text-secondary">
                {selected.shape === "windrow" ? "Полоса" : "Пятно"} ·{" "}
                {formatDistance(selected.lengthM)}
              </span>
            </p>
          ) : null}
          <ComparePickers a={pair.a} b={pair.b} actions={actions} />
          <p className="text-[12px] text-text-secondary">
            {intervalText(intervalOf(scenes, pair))}
          </p>
          <HonestyNote />
        </>
      }
      footer={<Footer onSwap={actions.swap} canSwap />}
    >
      {selected ? (
        <ObjectDynamicsBody
          candidate={selected}
          history={history}
          scenes={scenes}
          pair={pair}
          actions={actions}
        />
      ) : !isDemo && live.status === "ready" ? (
        <>
          <LiveSummary pair={pair} passes={passes} timeline={live.timeline} />
          <LiveChange pair={pair} passes={passes} />
          <LivePassList
            scenes={scenes}
            pair={pair}
            passes={passes}
            timeline={live.timeline}
            actions={actions}
          />
        </>
      ) : !isDemo && (live.status === "loading" || live.status === "error") ? (
        <LiveState live={live} />
      ) : (
        <>
          <AreaSummary
            pair={pair}
            a={sideTotals(histories, pair.a)}
            b={sideTotals(histories, pair.b)}
            detection={isDemo}
          />
          <ObjectDeltas rows={rows} pair={pair} />
        </>
      )}
    </InspectorFrame>
  );
}

export function CompareInspector() {
  const { hasCatalog } = useCompareData();
  return (
    <ShellSlot region="inspector">{hasCatalog ? <ComparePanel /> : <PlannedPanel />}</ShellSlot>
  );
}
