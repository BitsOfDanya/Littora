"use client";

import type { ReactNode } from "react";
import { useSceneCatalogState } from "@/data/scenes";
import type { SceneSummary } from "@/domain/scene";
import { formatPercent } from "@/lib/format/numbers";
import { formatUtcDateTime } from "@/lib/format/time";
import { useWorkspaceStore } from "@/state/workspace-store";
import { Button, IconButton } from "@/ui/button";
import { cn } from "@/ui/cn";
import { DemoTag } from "@/ui/demo-mark";
import {
  IconCaution,
  IconChevronLeft,
  IconChevronRight,
  IconNextUsable,
  IconPause,
  IconPlay,
} from "@/ui/icons";
import { Caps } from "@/ui/section";
import { ageLabel, sceneLimit } from "./rail-model";
import type { useSceneStepping } from "./use-scene-stepping";
import type { PlaybackSpeed } from "./use-scene-playback";

type Stepping = ReturnType<typeof useSceneStepping>;

type Playback = {
  playing: boolean;
  speed: PlaybackSpeed;
  toggle: () => void;
  cycleSpeed: () => void;
};

const STEP_BUTTON = "size-7";

export function RailHeader({
  label,
  sentence,
  demo,
}: {
  label: string;
  sentence: string;
  demo: boolean;
}) {
  return (
    <div className="flex h-[18px] min-w-0 items-center gap-1.5">
      <Caps className="text-text-secondary">{label}</Caps>
      <span className="hidden text-[11px] leading-[14px] whitespace-nowrap text-text-tertiary @[232px]:inline">
        {sentence}
      </span>
      {demo ? <DemoTag className="ml-auto" /> : null}
    </div>
  );
}

function ControlShell({ children }: { children: ReactNode }) {
  return (
    <div className="@container flex h-full min-w-0 flex-col justify-center gap-[3px] border-r border-line-hairline px-3 py-1.5">
      {children}
    </div>
  );
}

function cautionText(scene: SceneSummary): string | null {
  if (scene.usability === "unusable") return `${sceneLimit(scene)} — объекты не наблюдались`;
  if (scene.usability === "partial") return `${sceneLimit(scene)} — часть района закрыта`;
  return null;
}

function MetaLine({ scene, now }: { scene: SceneSummary; now: number }) {
  const caution = cautionText(scene);
  if (caution)
    return (
      <p className="flex min-w-0 items-center gap-1 text-[11px] leading-[14px] whitespace-nowrap text-state-caution">
        <IconCaution size={12} className="shrink-0" />
        <span className="min-w-0">{caution}</span>
      </p>
    );
  return (
    <p className="text-[11px] leading-[14px] whitespace-nowrap text-text-secondary">
      {scene.platform} · T{scene.mgrsTile} · <span className="@[236px]:hidden">обл.</span>
      <span className="hidden @[236px]:inline">облачность</span> {formatPercent(scene.cloudCover)} ·{" "}
      {ageLabel(scene.acquiredAt, now)}
    </p>
  );
}

export function SceneControlBlock({
  scene,
  isDemo,
  stepping,
  playback,
  now,
}: {
  scene: SceneSummary;
  isDemo: boolean;
  stepping: Stepping;
  playback: Playback;
  now: number;
}) {
  return (
    <ControlShell>
      <RailHeader label="Снимок" sentence="выбранный пролёт Sentinel-2" demo={isDemo} />
      <p className="font-mono text-[17px] leading-[22px] font-semibold whitespace-nowrap text-text-primary">
        {formatUtcDateTime(scene.acquiredAt)}
      </p>
      <MetaLine scene={scene} now={now} />
      <div role="group" aria-label="Шаг по пролётам" className="mt-0.5 flex items-center gap-1">
        <IconButton
          label="Предыдущий пролёт"
          shortcut="["
          className={STEP_BUTTON}
          disabled={!stepping.canStepBack}
          onClick={() => stepping.step(-1)}
        >
          <IconChevronLeft />
        </IconButton>
        <IconButton
          label="Следующий пролёт"
          shortcut="]"
          className={STEP_BUTTON}
          disabled={!stepping.canStepForward}
          onClick={() => stepping.step(1)}
        >
          <IconChevronRight />
        </IconButton>
        <IconButton
          label={playback.playing ? "Пауза" : "Пуск"}
          shortcut="Space"
          pressed={playback.playing}
          className={STEP_BUTTON}
          onClick={playback.toggle}
        >
          {playback.playing ? <IconPause /> : <IconPlay />}
        </IconButton>
        <button
          type="button"
          onClick={playback.cycleSpeed}
          title={`Скорость воспроизведения ${playback.speed}× · нажмите, чтобы сменить`}
          aria-label={`Скорость воспроизведения ${playback.speed}×`}
          className="grid h-7 w-8 shrink-0 place-items-center rounded-[var(--radius-ctl)] border border-line-control bg-surface-panel font-mono text-[12px] text-text-secondary hover:bg-surface-raised hover:text-text-primary"
        >
          {playback.speed}×
        </button>
        <Button
          size="md"
          className="px-2"
          disabled={!stepping.canStepToUsable}
          title="Следующий пригодный пролёт · Shift ]"
          aria-keyshortcuts="Shift+BracketRight"
          onClick={() => stepping.step(1, true)}
        >
          <IconNextUsable size={14} className="hidden @[228px]:block" />
          <span className="hidden @[200px]:inline">Пригодный</span>
          <IconNextUsable size={14} className="@[200px]:hidden" />
        </Button>
      </div>
    </ControlShell>
  );
}

const CATALOG_TITLE = {
  loading: "Каталог снимков…",
  error: "Каталог недоступен",
  ready: "Снимков нет",
} as const;

export function PlannedControlBlock() {
  const setDemoFixtures = useWorkspaceStore((state) => state.setDemoFixtures);
  const catalog = useSceneCatalogState();
  const known =
    catalog.status === "loading" || catalog.status === "error" || catalog.status === "ready";
  const subline =
    catalog.status === "error"
      ? catalog.message
      : known
        ? `${catalog.query.dateFrom} — ${catalog.query.dateTo}`
        : "появится с каталогом Sentinel-2";
  return (
    <ControlShell>
      <RailHeader label="Снимок" sentence="выбранный пролёт Sentinel-2" demo={false} />
      <p className="text-[15px] leading-5 font-semibold whitespace-nowrap text-text-primary">
        {known ? CATALOG_TITLE[catalog.status] : "Снимок не выбран"}
      </p>
      <p className="truncate text-[11px] leading-[14px] text-text-secondary">{subline}</p>
      <div className="mt-0.5 flex items-center gap-1">
        <IconButton label="Предыдущий пролёт" shortcut="[" className={STEP_BUTTON} disabled>
          <IconChevronLeft />
        </IconButton>
        <IconButton label="Следующий пролёт" shortcut="]" className={STEP_BUTTON} disabled>
          <IconChevronRight />
        </IconButton>
        {catalog.status === "error" ? (
          <Button size="md" className={cn("min-w-0 px-2")} onClick={catalog.retry}>
            Повторить
          </Button>
        ) : known ? null : (
          <Button size="md" className={cn("min-w-0 px-2")} onClick={() => setDemoFixtures(true)}>
            Показать на демо-данных
          </Button>
        )}
      </div>
    </ControlShell>
  );
}
