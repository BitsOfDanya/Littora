"use client";

import type { ReactNode } from "react";
import { useCandidates } from "@/data/candidates";
import { ObjectTable } from "@/features/objects/object-table";
import { ObjectsSummary } from "@/features/objects/objects-summary";
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

export function ObjectsTab({ density }: { density: RowDensity }) {
  const sourced = useCandidates();
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
  if (sourced.origin === "none" && !lead) return null;
  return (
    <FooterBar density={density}>
      {lead}
      {sourced.origin === "none" ? null : <ObjectsSummary candidates={sourced.data} />}
    </FooterBar>
  );
}

export function useObjectsCount(): number | null {
  const sourced = useCandidates();
  return sourced.origin === "none" ? null : sourced.data.length;
}
