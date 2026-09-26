"use client";

import { type ReactNode, useState } from "react";
import { useCandidates } from "@/data/candidates";
import { formatDay } from "@/features/analysis/format";
import { useAnalysisZones, useCurrentAnalysis } from "@/features/analysis/use-analysis";
import { isLikelyNotDebris } from "@/features/analysis/zones";
import { ObjectTable } from "@/features/objects/object-table";
import { ObjectsSummary } from "@/features/objects/objects-summary";
import { useSelectZone } from "@/features/objects/use-select-zone";
import { ZoneTable, ZonesSummary } from "@/features/objects/zone-table";
import { useCapability } from "@/features/system/use-capabilities";
import { DemoRibbon } from "@/ui/demo-mark";
import { PlannedState } from "@/ui/planned";
import { FooterBar } from "./cartouche-footer";
import type { RowDensity } from "./layer-row";
import { DemoAction } from "./planned-group-note";

function ObjectsPlanned() {
  return (
    <PlannedState
      title="Детекция мусора — не подключено"
      capability="debris_detection"
      requirement="сцена Sentinel-2 L2A и модель детекции."
      action={<DemoAction />}
      className="m-3 p-3"
    >
      Пятна-кандидаты появятся здесь списком по приоритету — это клавиатурное зеркало карты.
    </PlannedState>
  );
}

function ObjectsNoZones() {
  const analysis = useCurrentAnalysis().data;
  return (
    <p className="m-3 text-[12px] leading-4 text-text-secondary">
      {analysis
        ? `В анализе за ${formatDay(analysis.request.date)} детектор зон не выделил: ${analysis.detection.reason}.`
        : "Зоны детектора появятся здесь списком по вероятности после анализа района в «Мониторинге»."}
    </p>
  );
}

function RealZones({ density }: { density: RowDensity }) {
  const source = useAnalysisZones();
  const { selectedId, select } = useSelectZone();
  const [hideLikely, setHideLikely] = useState(false);
  if (!source) return null;
  const flagged = source.zones.filter(isLikelyNotDebris).length;
  const zones = hideLikely ? source.zones.filter((zone) => !isLikelyNotDebris(zone)) : source.zones;
  return (
    <div className="flex flex-col">
      {flagged ? (
        <label className="flex items-center gap-2 px-3 py-1.5 text-[11px] text-text-secondary">
          <input
            type="checkbox"
            checked={hideLikely}
            onChange={(event) => setHideLikely(event.target.checked)}
          />
          Скрыть вероятные суда и сооружения ({flagged})
        </label>
      ) : null}
      <ZoneTable
        zones={zones}
        threshold={source.threshold}
        selectedId={selectedId}
        onSelect={select}
        density={density}
      />
    </div>
  );
}

export function ObjectsTab({ density }: { density: RowDensity }) {
  const sourced = useCandidates();
  const zones = useAnalysisZones();
  const detector = useCapability("debris_detection");
  if (sourced.origin === "none" && zones) return <RealZones density={density} />;
  if (sourced.origin === "none" && detector === "available") return <ObjectsNoZones />;
  if (sourced.origin === "none") return <ObjectsPlanned />;
  return (
    <div className="flex flex-col">
      {sourced.origin === "demo" ? (
        <DemoRibbon source="demo/candidates" className="border-t-0 px-3" />
      ) : null}
      <ObjectTable candidates={sourced.data} density={density} />
    </div>
  );
}

export function ObjectsFooter({ density, lead }: { density: RowDensity; lead?: ReactNode }) {
  const sourced = useCandidates();
  const zones = useAnalysisZones();
  if (sourced.origin === "none" && !zones && !lead) return null;
  return (
    <FooterBar density={density}>
      {lead}
      {sourced.origin !== "none" ? (
        <ObjectsSummary candidates={sourced.data} />
      ) : zones ? (
        <ZonesSummary zones={zones.zones} />
      ) : null}
    </FooterBar>
  );
}

export function useObjectsCount(): number | null {
  const sourced = useCandidates();
  const zones = useAnalysisZones();
  if (sourced.origin !== "none") return sourced.data.length;
  return zones ? zones.zones.length : null;
}
