"use client";

import { useMemo } from "react";
import type { DossierData } from "@/data/monitor-dossier";
import type { DebrisCandidate } from "@/domain/detection";
import { useHotkey } from "@/features/shell/hotkeys";
import { formatNumber } from "@/lib/format/numbers";
import { useShellUiStore } from "@/state/shell-ui-store";
import { Button } from "@/ui/button";
import { DemoTag } from "@/ui/demo-mark";
import { IconPin } from "@/ui/icons";
import { Kbd } from "@/ui/kbd";
import { PanelSection } from "@/ui/section";
import { shortCandidateId } from "@/features/monitor/map/label-text";
import { useSpectrumPinsStore } from "../spectrum-pins-store";
import {
  SpectrumChart,
  SpectrumLegendSample,
  type SpectrumSeries,
  type SpectrumTone,
} from "./spectrum-chart";

const FDI_THRESHOLD = 0.01;

export function SpectrumSection({
  candidate,
  dossier,
  isDemo,
}: {
  candidate: DebrisCandidate;
  dossier: DossierData;
  isDemo: boolean;
}) {
  const pins = useSpectrumPinsStore((state) => state.pins);
  const togglePin = useSpectrumPinsStore((state) => state.toggle);
  const modalOpen = useShellUiStore((state) => state.shortcutSheetOpen);
  const pinned = pins.some((pin) => pin.candidateId === candidate.id);
  const { fdi, ndvi } = candidate.spectrum.indices;

  const toggle = () =>
    togglePin({ candidateId: candidate.id, bands: candidate.spectrum.candidate });
  useHotkey("KeyP", toggle, { enabled: !modalOpen });

  const series = useMemo<SpectrumSeries[]>(
    () => [
      ...dossier.references.map((reference) => ({
        key: reference.key,
        label: reference.label,
        tone: reference.key as SpectrumTone,
        bands: reference.bands,
      })),
      ...pins
        .filter((pin) => pin.candidateId !== candidate.id)
        .map((pin) => ({
          key: `pin-${pin.candidateId}`,
          label: `${shortCandidateId(pin.candidateId)} · закреплено`,
          tone: "pinned" as const,
          bands: pin.bands,
        })),
      {
        key: "spot",
        label: "Пятно ± 1σ",
        tone: "spot" as const,
        bands: candidate.spectrum.candidate,
        sigma: dossier.sigma,
      },
    ],
    [dossier, pins, candidate],
  );

  const legend = [...series].sort((a, b) => (a.tone === "spot" ? -1 : b.tone === "spot" ? 1 : 0));

  return (
    <PanelSection
      id="dossier-spectrum"
      index="03"
      title="Спектр Sentinel-2"
      className="scroll-mt-[var(--inspector-pin,40px)]"
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <p className="font-mono text-[12px] leading-4 text-text-primary">
          FDI {formatNumber(fdi, 3)}
          <span className="text-text-tertiary"> · порог {formatNumber(FDI_THRESHOLD, 3)} · </span>
          NDVI {formatNumber(ndvi, 2)}
        </p>
        {isDemo ? <DemoTag /> : null}
        <Button
          size="sm"
          className="ml-auto"
          aria-pressed={pinned}
          aria-keyshortcuts="P"
          title="Закрепить спектр, чтобы сравнить с другим пятном · P"
          onClick={toggle}
        >
          <IconPin size={13} />
          {pinned ? "Открепить" : "Закрепить"}
          <Kbd>P</Kbd>
        </Button>
      </div>
      <SpectrumChart
        series={series}
        illustration={isDemo}
        title={`Спектр ${candidate.id} по каналам Sentinel-2 и эталонные спектры`}
      />
      <ul className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] leading-[14px] text-text-secondary">
        {legend.map((entry) => (
          <li key={entry.key} className="flex items-center gap-1.5">
            <SpectrumLegendSample tone={entry.tone} />
            {entry.label}
          </li>
        ))}
      </ul>
      <p className="text-[11px] leading-[14px] text-text-tertiary">
        Полосы — ширина каналов; FDI считается по B06 · B08 · B11 (светлые). Эталоны смешаны с водой
        при той же доле покрытия ({formatNumber(candidate.coverage.value * 100, 0)} %).
      </p>
      {isDemo ? (
        <p className="flex items-center gap-1.5 text-[11px] leading-[14px] text-text-secondary">
          Синтетический спектр, не измерение · эталонные спектры иллюстративные
          <DemoTag />
        </p>
      ) : null}
    </PanelSection>
  );
}
