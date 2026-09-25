"use client";

import type { DossierData } from "@/data/monitor-dossier";
import { formatLngLat } from "@/lib/format/coordinates";
import { formatDistance, formatPercent } from "@/lib/format/numbers";
import { usePreferencesStore } from "@/state/preferences-store";
import { KeyValue, KeyValueList } from "@/ui/key-value";
import { PlannedTag } from "@/ui/planned";
import { CollapsibleSection } from "./collapsible-section";
import { CopyButton } from "./copy-button";

const GLINT_WORD = { low: "низкий", moderate: "умеренный", high: "высокий" } as const;

function acquiredStamp(iso: string): string {
  return `${iso.slice(0, 10)} ${iso.slice(11, 19)}Z`;
}

export function SceneSection({
  dossier,
  open,
  onToggle,
  isDemo,
}: {
  dossier: DossierData;
  open: boolean;
  onToggle: (open: boolean) => void;
  isDemo: boolean;
}) {
  const format = usePreferencesStore((state) => state.coordinateFormat);
  const { candidate, scene } = dossier;
  const baseline = /_(N\d{4})_/.exec(candidate.sceneId)?.[1] ?? "—";
  return (
    <CollapsibleSection
      id="dossier-scene"
      index="06"
      title="Сцена и происхождение"
      open={open}
      onToggle={onToggle}
    >
      <KeyValueList>
        <KeyValue label="ID сцены">
          <span className="font-mono text-[11px] leading-[14px] font-normal break-all">
            {candidate.sceneId}
          </span>
          <CopyButton value={candidate.sceneId} label="Скопировать ID сцены" />
        </KeyValue>
        {scene ? (
          <>
            <KeyValue label="Спутник · тайл · орбита">
              {scene.platform} · T{scene.mgrsTile} · R{String(scene.relativeOrbit).padStart(3, "0")}
            </KeyValue>
            <KeyValue label="Время съёмки">{acquiredStamp(scene.acquiredAt)}</KeyValue>
            <KeyValue label="Облачность">
              сцена {formatPercent(scene.cloudCover)} · над пятном{" "}
              {formatPercent(dossier.cloudOverSpot)}
            </KeyValue>
            <KeyValue label="Солнце · блики">
              зенит {Math.round(scene.sunZenithDeg)}° · риск бликов {GLINT_WORD[scene.sunGlintRisk]}
            </KeyValue>
            <KeyValue label="Обработка">
              {scene.processingLevel} · {baseline}
            </KeyValue>
          </>
        ) : null}
        <KeyValue label="Модель" tag={isDemo ? <PlannedTag capability="debris_detection" /> : null}>
          {isDemo ? "не подключена" : `${candidate.model.name} · ${candidate.model.version}`}
        </KeyValue>
        <KeyValue label="Центр">{formatLngLat(candidate.centroid, format)}</KeyValue>
        <KeyValue label="До берега · до устья">
          {formatDistance(candidate.distanceToCoastM)} · {dossier.mouth.name}{" "}
          {formatDistance(dossier.mouth.distanceM)}
        </KeyValue>
      </KeyValueList>
    </CollapsibleSection>
  );
}
