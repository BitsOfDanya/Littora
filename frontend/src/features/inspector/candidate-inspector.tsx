"use client";

import { findAoi } from "@/config/aois";
import { useCandidates } from "@/data/candidates";
import { ShellSlot } from "@/features/shell/shell-slots";
import { useWorkspaceStore } from "@/state/workspace-store";
import { Button } from "@/ui/button";
import { PlannedState } from "@/ui/planned";
import { CandidateDossier } from "./candidate-dossier";
import { InspectorFrame } from "./parts/inspector-frame";

function PlannedDossier({ candidateId }: { candidateId: string }) {
  const aoiId = useWorkspaceStore((state) => state.aoiId);
  const selectCandidate = useWorkspaceStore((state) => state.selectCandidate);
  const setDemoFixtures = useWorkspaceStore((state) => state.setDemoFixtures);
  return (
    <InspectorFrame
      label={`Досье ${candidateId}`}
      eyebrow="Досье пятна-кандидата"
      crumbs={[{ label: findAoi(aoiId)?.name ?? "Район", serif: true }, { label: "Досье" }]}
      onClose={() => selectCandidate(null)}
      header={
        <p className="font-mono text-[15px] leading-5 font-semibold text-text-secondary">
          {candidateId}
        </p>
      }
    >
      <div className="p-4">
        <PlannedState
          title="Детекция мусора — не подключено"
          capability="debris_detection"
          requirement="сцена Sentinel-2 L2A и модель детекции."
          action={<Button onClick={() => setDemoFixtures(true)}>Показать на демо-данных</Button>}
        >
          Контуры кандидатов, доля покрытия, уверенность и неопределённость появятся здесь как слои.
          Досье объекта будет собрано из снимка, спектра и истории пролётов.
        </PlannedState>
      </div>
    </InspectorFrame>
  );
}

export function CandidateInspector() {
  const selectedId = useWorkspaceStore((state) => state.selectedCandidateId);
  const candidates = useCandidates();

  if (!selectedId) return null;
  if (candidates.origin === "none")
    return (
      <ShellSlot region="inspector">
        <PlannedDossier candidateId={selectedId} />
      </ShellSlot>
    );
  const candidate = candidates.data.find((entry) => entry.id === selectedId);
  if (!candidate) return null;

  return (
    <ShellSlot region="inspector">
      <CandidateDossier
        candidate={candidate}
        candidates={candidates.data}
        isDemo={candidates.origin === "demo"}
      />
    </ShellSlot>
  );
}
