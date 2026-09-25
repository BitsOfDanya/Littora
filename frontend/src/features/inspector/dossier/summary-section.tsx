"use client";

import { useMemo } from "react";
import type { DebrisCandidate } from "@/domain/detection";
import type { SceneSummary } from "@/domain/scene";
import { orderByPriority } from "@/features/objects/object-order";
import { ageLabel } from "@/features/time-rail/rail-model";
import { shortDay } from "@/features/time-rail/rail-tracks";
import { useNow } from "@/features/time-rail/use-now";
import { formatNumber, formatSigned } from "@/lib/format/numbers";
import { formatUtcTime } from "@/lib/format/time";
import { ConfidenceGlyph, CONFIDENCE_WORD, PriorityBars, PRIORITY_WORD } from "@/ui/indicators";
import { PanelSection } from "@/ui/section";
import { Readout, ReadoutGrid } from "../parts/readout-grid";

const CLASS_THRESHOLD = 0.5;
const DAY_MS = 86_400_000;

const percent = (value: number) => formatNumber(value * 100, 0);
const km2 = (value: number) => formatNumber(value / 1_000_000, value >= 1_000_000 ? 2 : 3);

export function SummarySection({
  candidate,
  candidates,
  scene,
  areaInterval,
  isDemo,
}: {
  candidate: DebrisCandidate;
  candidates: readonly DebrisCandidate[];
  scene: SceneSummary | undefined;
  areaInterval: readonly [number, number];
  isDemo: boolean;
}) {
  const now = useNow();
  const rank = useMemo(
    () => orderByPriority(candidates).findIndex((entry) => entry.id === candidate.id) + 1,
    [candidates, candidate.id],
  );
  const change = candidate.change;
  const days = change
    ? Math.round(
        (Date.parse(candidate.observedAt) - Date.parse(change.previousObservedAt)) / DAY_MS,
      )
    : 0;
  const platform = scene?.platform ?? candidate.sceneId.slice(0, 3);
  const stamp = `${platform} T${scene?.mgrsTile ?? "—"} ${candidate.observedAt.slice(0, 10)} ${formatUtcTime(candidate.observedAt)}`;

  return (
    <PanelSection
      id="dossier-summary"
      index="01"
      title="Сводка"
      className="scroll-mt-[var(--inspector-pin,40px)]"
    >
      <ReadoutGrid>
        <Readout
          label="Уверенность"
          glyph={<ConfidenceGlyph confidence={candidate.confidence.class} withWord={false} />}
          value={formatNumber(candidate.confidence.score, 2)}
          unit={CONFIDENCE_WORD[candidate.confidence.class]}
          interval={`порог класса ${formatNumber(CLASS_THRESHOLD, 2)}`}
        />
        <Readout
          label="Доля покрытия"
          value={percent(candidate.coverage.value)}
          unit="%"
          interval={`90 % ДИ ${percent(candidate.coverage.low)}–${percent(candidate.coverage.high)}`}
        />
        <Readout
          label="Площадь пятна"
          value={km2(candidate.areaM2)}
          unit="км²"
          interval={`90 % ДИ ${km2(areaInterval[0])}–${km2(areaInterval[1])}`}
        />
        <Readout
          label="Изменение"
          glyph={
            change ? (
              <span aria-hidden className="text-[12px] text-text-secondary">
                {change.areaDeltaRatio >= 0 ? "▲" : "▼"}
              </span>
            ) : undefined
          }
          value={change ? formatSigned(change.areaDeltaRatio * 100, 0) : "—"}
          unit={change ? "%" : undefined}
          interval={
            change
              ? `к ${shortDay(change.previousObservedAt)} · за ${days} сут`
              : "первое наблюдение"
          }
          tone={change ? "primary" : "secondary"}
        />
        <Readout
          label="Последнее наблюдение"
          value={`${shortDay(candidate.observedAt)} ${formatUtcTime(candidate.observedAt)}`}
          interval={`${ageLabel(candidate.observedAt, now)} · ${platform}`}
        />
        <Readout
          label="Приоритет проверки"
          glyph={<PriorityBars priority={candidate.priority} />}
          value={PRIORITY_WORD[candidate.priority]}
          valueFont="sans"
          interval={`№ ${rank} из ${candidates.length}`}
        />
      </ReadoutGrid>
      <p className="text-[11px] leading-[14px] text-text-tertiary">
        Источник: {isDemo ? "фикстура demo/candidates" : candidate.model.name} · сцена {stamp} ·{" "}
        {isDemo ? "модель не подключена" : `модель ${candidate.model.version}`}
      </p>
    </PanelSection>
  );
}
