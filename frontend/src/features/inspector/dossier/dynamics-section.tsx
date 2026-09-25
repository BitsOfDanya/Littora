"use client";

import { useMemo } from "react";
import type { PassObservation } from "@/data/monitor-passes";
import { useScenes } from "@/data/scenes";
import { useSelectedScene } from "@/features/time-rail/use-selected-scene";
import { useWorkspaceStore } from "@/state/workspace-store";
import { DemoTag } from "@/ui/demo-mark";
import { PanelSection } from "@/ui/section";
import { ObservationSeries, type SeriesPoint } from "../parts/observation-series";

function toPoint(observation: PassObservation, cloudCover: number | undefined): SeriesPoint {
  if (observation.state === "found" && observation.coverage)
    return {
      id: observation.sceneId,
      time: observation.observedAt,
      state: "observed",
      value: observation.coverage.value,
      low: observation.coverage.low,
      high: observation.coverage.high,
    };
  if (observation.state === "not-found")
    return { id: observation.sceneId, time: observation.observedAt, state: "not-found" };
  return {
    id: observation.sceneId,
    time: observation.observedAt,
    state: "cloudy",
    cloudCover,
  };
}

export function DynamicsSection({
  candidateId,
  observations,
  isDemo,
}: {
  candidateId: string;
  observations: readonly PassObservation[];
  isDemo: boolean;
}) {
  const scenes = useScenes();
  const { scene } = useSelectedScene();
  const selectScene = useWorkspaceStore((state) => state.selectScene);
  const cloudBySceneId = useMemo(
    () =>
      new Map(
        (scenes.origin === "none" ? [] : scenes.data).map((entry) => [entry.id, entry.cloudCover]),
      ),
    [scenes],
  );
  const points = useMemo(
    () => observations.map((entry) => toPoint(entry, cloudBySceneId.get(entry.sceneId))),
    [observations, cloudBySceneId],
  );
  const found = observations.filter((entry) => entry.state === "found").length;
  const usable = observations.filter((entry) => entry.state !== "cloudy").length;

  return (
    <PanelSection
      id="dossier-dynamics"
      index="04"
      title="Динамика"
      aside={isDemo ? <DemoTag /> : null}
      className="scroll-mt-[var(--inspector-pin,40px)]"
    >
      <ObservationSeries
        points={points}
        selectedId={scene?.id ?? null}
        unit="Доля покрытия, % по пролётам Sentinel-2"
        title={`Доля покрытия ${candidateId} по пролётам`}
        onSelect={selectScene}
      />
      <p className="text-[12px] leading-4 text-text-primary">
        Найдено в {found} из {usable} пригодных пролётов
        <span className="text-text-tertiary"> · щелчок по точке — выбрать пролёт на шкале</span>
      </p>
    </PanelSection>
  );
}
