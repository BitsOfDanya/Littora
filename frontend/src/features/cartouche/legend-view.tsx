"use client";

import type { MapModeId } from "@/config/layers";
import { useWorkspaceStore } from "@/state/workspace-store";
import { BasemapGroup } from "./basemap-group";
import { CompareGroup } from "./compare-group";
import { LegendNote } from "./layer-legend";
import type { RowDensity } from "./layer-row";
import { LayerRowsGroup } from "./layer-rows-group";
import { PlannedGroupNote, PlannedLine } from "./planned-group-note";
import { SceneGroup } from "./scene-group";
import { useDemoActive, useLayerTruth } from "./use-layer-truth";

type ViewProps = { mode: MapModeId; showAll: boolean; density: RowDensity };

function ForecastGroup({ mode, showAll, density }: ViewProps) {
  const truthOf = useLayerTruth();
  const demoActive = useDemoActive();
  const hasSelection = useWorkspaceStore((state) => state.selectedCandidateId !== null);
  return (
    <LayerRowsGroup
      mode={mode}
      group="forecast"
      truthOf={truthOf}
      showAll={showAll}
      density={density}
      plannedNote={<PlannedGroupNote group="forecast" />}
      lead={hasSelection ? null : <LegendNote>Выберите пятно, чтобы построить прогноз</LegendNote>}
      footnote={demoActive ? "Поле течений и частицы — синтетические, для макета" : undefined}
    />
  );
}

function ResultsGroup({ mode, showAll, density }: ViewProps) {
  const truthOf = useLayerTruth();
  const note =
    mode === "monitor" ? (
      <PlannedGroupNote group="results" />
    ) : (
      <PlannedLine capability="debris_detection">
        Контуры кандидатов появятся с детекцией
      </PlannedLine>
    );
  return (
    <LayerRowsGroup
      mode={mode}
      group="results"
      truthOf={truthOf}
      showAll={showAll}
      density={density}
      plannedNote={note}
    />
  );
}

function PrimaryGroup({ mode, showAll, density }: ViewProps) {
  const truthOf = useLayerTruth();
  switch (mode) {
    case "monitor":
      return <SceneGroup mode={mode} truthOf={truthOf} density={density} />;
    case "timeline":
      return <CompareGroup mode={mode} truthOf={truthOf} showAll={showAll} density={density} />;
    case "forecast":
      return <ForecastGroup mode={mode} showAll={showAll} density={density} />;
    case "survey":
      return (
        <LayerRowsGroup
          mode={mode}
          group="survey"
          truthOf={truthOf}
          showAll={showAll}
          density={density}
          plannedNote={<PlannedGroupNote group="survey" />}
        />
      );
  }
}

export function LegendView({ mode, showAll, density }: ViewProps) {
  const truthOf = useLayerTruth();
  return (
    <div className="flex flex-col">
      <BasemapGroup mode={mode} density={density} />
      <PrimaryGroup mode={mode} showAll={showAll} density={density} />
      <ResultsGroup mode={mode} showAll={showAll} density={density} />
      <LayerRowsGroup
        mode={mode}
        group="conditions"
        truthOf={truthOf}
        showAll={showAll}
        density={density}
        plannedNote={
          <PlannedLine capability="scene_catalog">
            Маска облаков и контур сцены придут с каталогом снимков
          </PlannedLine>
        }
      />
      <LayerRowsGroup
        mode={mode}
        group="context"
        truthOf={truthOf}
        showAll={showAll}
        density={density}
        defaultOpen={false}
      />
    </div>
  );
}
