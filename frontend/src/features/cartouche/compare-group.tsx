"use client";

import type { MapModeId } from "@/config/layers";
import type { SceneSummary } from "@/domain/scene";
import { formatPercent } from "@/lib/format/numbers";
import { useWorkspaceStore } from "@/state/workspace-store";
import { Button } from "@/ui/button";
import { IconSwap } from "@/ui/icons";
import { SeverityGlyph } from "@/ui/indicators";
import { Kbd } from "@/ui/kbd";
import { LayerRowsGroup } from "./layer-rows-group";
import type { RowDensity } from "./layer-row";
import { useSceneList } from "./use-current-scene";
import type { LayerTruthResolver } from "./use-layer-truth";

type ComparePair = { a: SceneSummary | undefined; b: SceneSummary | undefined };

function useComparePair(): ComparePair {
  const { scenes } = useSceneList();
  const beforeId = useWorkspaceStore((state) => state.compare.beforeSceneId);
  const afterId = useWorkspaceStore((state) => state.compare.afterSceneId);
  return {
    a: scenes.find((scene) => scene.id === beforeId) ?? scenes.at(-3),
    b: scenes.find((scene) => scene.id === afterId) ?? scenes.at(-1),
  };
}

function CloudNote({ scene }: { scene: SceneSummary }) {
  const cloud = formatPercent(scene.cloudCover).replace(" ", " ");
  if (scene.usability === "usable")
    return <span className="text-text-secondary">облачность {cloud}</span>;
  return (
    <span className="inline-flex items-center gap-1 text-state-caution">
      <SeverityGlyph severity="caution" size={12} />
      облачно {cloud}
    </span>
  );
}

function CompareRow({
  letter,
  scene,
  mosaicYear,
}: {
  letter: "A" | "B";
  scene: SceneSummary | undefined;
  mosaicYear: number;
}) {
  return (
    <div className="flex min-h-7 flex-wrap items-center gap-x-2 gap-y-0.5 text-[12px] leading-4">
      <span
        aria-hidden
        className="grid size-[18px] shrink-0 place-items-center bg-primary-fill font-mono text-[11px] font-semibold text-primary-text"
      >
        {letter}
      </span>
      <span className="sr-only">{letter === "A" ? "Дата A" : "Дата B"}</span>
      {scene ? (
        <>
          <span className="font-mono text-text-primary">{scene.acquiredAt.slice(0, 10)}</span>
          <span className="font-mono text-text-secondary">{scene.platform}</span>
          <CloudNote scene={scene} />
        </>
      ) : (
        <span className="text-text-secondary">мозаика {mosaicYear}</span>
      )}
    </div>
  );
}

function CompareLead() {
  const { a, b } = useComparePair();
  const updateCompare = useWorkspaceStore((state) => state.updateCompare);
  const canSwap = Boolean(a && b);
  return (
    <div className="flex flex-col gap-0.5 pt-1 pb-1.5">
      <CompareRow letter="A" scene={a} mosaicYear={2024} />
      <CompareRow letter="B" scene={b} mosaicYear={2025} />
      <div className="pt-1">
        <Button
          size="sm"
          disabled={!canSwap}
          title={canSwap ? "Поменять A и B · X" : "Нужны два снимка из каталога"}
          icon={<IconSwap size={12} />}
          onClick={() => {
            if (a && b) updateCompare({ beforeSceneId: b.id, afterSceneId: a.id });
          }}
        >
          Поменять A и B<Kbd className="h-4 min-w-4">X</Kbd>
        </Button>
      </div>
    </div>
  );
}

type CompareGroupProps = {
  mode: MapModeId;
  truthOf: LayerTruthResolver;
  showAll: boolean;
  density: RowDensity;
};

export function CompareGroup({ mode, truthOf, showAll, density }: CompareGroupProps) {
  const { isDemo } = useSceneList();
  return (
    <LayerRowsGroup
      mode={mode}
      group="compare"
      truthOf={truthOf}
      showAll={showAll}
      density={density}
      demo={isDemo}
      showPlanned
      lead={<CompareLead />}
    />
  );
}
