"use client";

import { useMemo, useState } from "react";
import { findAoi } from "@/config/aois";
import { useCandidateDossier } from "@/data/monitor-dossier";
import { useCandidateObservations, usePassCandidates } from "@/data/monitor-passes";
import type { DebrisCandidate } from "@/domain/detection";
import { fitAoi } from "@/features/map/camera";
import { useMainMap } from "@/features/map/use-main-map";
import { shortDay } from "@/features/time-rail/rail-tracks";
import { useWorkspaceStore } from "@/state/workspace-store";
import { PanelSection } from "@/ui/section";
import { ConfuserList } from "./dossier/confuser-list";
import { DossierFooter } from "./dossier/dossier-footer";
import { DossierHeader } from "./dossier/dossier-header";
import { DynamicsSection } from "./dossier/dynamics-section";
import { EvidenceChip } from "./dossier/evidence-chip";
import { JournalSection } from "./dossier/journal-section";
import { SceneSection } from "./dossier/scene-section";
import { SpectrumSection } from "./dossier/spectrum-section";
import { SummarySection } from "./dossier/summary-section";
import { InspectorFrame } from "./parts/inspector-frame";
import { JumpNav, type JumpTarget } from "./parts/jump-nav";

const JUMP_TARGETS: readonly JumpTarget[] = [
  { id: "dossier-summary", label: "Сводка" },
  { id: "dossier-evidence", label: "Снимок" },
  { id: "dossier-spectrum", label: "Спектр" },
  { id: "dossier-dynamics", label: "Динамика" },
  { id: "dossier-doubts", label: "Сомнения" },
  { id: "dossier-scene", label: "Сцена" },
];

const TOP_ID = "dossier-top";

type CandidateDossierProps = {
  candidate: DebrisCandidate;
  candidates: readonly DebrisCandidate[];
  isDemo: boolean;
};

function useCrumbs(candidate: DebrisCandidate) {
  const map = useMainMap();
  const aoiId = useWorkspaceStore((state) => state.aoiId);
  const selectScene = useWorkspaceStore((state) => state.selectScene);
  const aoi = findAoi(aoiId);
  return useMemo(
    () => [
      {
        label: aoi?.name ?? "Район",
        serif: true,
        onSelect: aoi && map ? () => fitAoi(map, aoi) : undefined,
      },
      { label: shortDay(candidate.observedAt), onSelect: () => selectScene(candidate.sceneId) },
      {
        label: "Досье",
        onSelect: () => document.getElementById(TOP_ID)?.scrollIntoView({ block: "start" }),
      },
    ],
    [aoi, map, candidate, selectScene],
  );
}

export function CandidateDossier({ candidate, candidates, isDemo }: CandidateDossierProps) {
  const selectCandidate = useWorkspaceStore((state) => state.selectCandidate);
  const crumbs = useCrumbs(candidate);
  const dossierSourced = useCandidateDossier(candidate.id);
  const dossier = dossierSourced.origin === "none" ? null : dossierSourced.data;
  const observationsSourced = useCandidateObservations();
  const observations =
    observationsSourced.origin === "none" ? undefined : observationsSourced.data[candidate.id];
  const passSourced = usePassCandidates(candidate.sceneId);
  const cells =
    passSourced.origin === "none"
      ? []
      : (passSourced.data.find((entry) => entry.candidate.id === candidate.id)?.cells ?? []);
  const [sceneOpen, setSceneOpen] = useState(false);
  const [journalOpen, setJournalOpen] = useState(false);

  return (
    <InspectorFrame
      label={`Досье ${candidate.id}`}
      eyebrow="Досье пятна-кандидата"
      crumbs={crumbs}
      demoSource={isDemo ? "demo/candidates" : null}
      onClose={() => selectCandidate(null)}
      selectionRule
      pin="nav"
      header={<DossierHeader candidate={candidate} />}
      nav={
        <JumpNav
          targets={JUMP_TARGETS}
          dense
          onNavigate={(id) => {
            if (id === "dossier-scene") setSceneOpen(true);
          }}
        />
      }
      footer={<DossierFooter candidateId={candidate.id} />}
    >
      <span id={TOP_ID} className="block scroll-mt-40" />
      <SummarySection
        candidate={candidate}
        candidates={candidates}
        scene={dossier?.scene}
        areaInterval={dossier?.areaInterval ?? [candidate.areaM2, candidate.areaM2]}
        isDemo={isDemo}
      />
      <PanelSection
        id="dossier-evidence"
        index="02"
        title="Снимок"
        className="scroll-mt-[var(--inspector-pin,40px)]"
      >
        <EvidenceChip
          geometry={candidate.geometry}
          cells={cells}
          confidence={candidate.confidence.class}
          focus={candidate.centroid}
        />
      </PanelSection>
      {dossier ? <SpectrumSection candidate={candidate} dossier={dossier} isDemo={isDemo} /> : null}
      {observations ? (
        <DynamicsSection candidateId={candidate.id} observations={observations} isDemo={isDemo} />
      ) : null}
      {dossier ? <ConfuserList rows={dossier.confusers} isDemo={isDemo} /> : null}
      {dossier ? (
        <SceneSection dossier={dossier} open={sceneOpen} onToggle={setSceneOpen} isDemo={isDemo} />
      ) : null}
      <JournalSection
        candidateId={candidate.id}
        fixture={dossier?.journal ?? []}
        open={journalOpen}
        onToggle={setJournalOpen}
        isDemo={isDemo}
      />
    </InspectorFrame>
  );
}
