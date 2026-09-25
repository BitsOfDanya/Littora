"use client";

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { WORKSPACE_MODES } from "@/config/modes";
import { useCandidates } from "@/data/candidates";
import { ApiStatusLabel, SystemDetails } from "@/features/system/backend-status";
import { useApiStatus } from "@/features/system/use-api-status";
import { useCapabilitySummary } from "@/features/system/use-capabilities";
import { useShellUiStore } from "@/state/shell-ui-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { cn } from "@/ui/cn";
import { DemoTag } from "@/ui/demo-mark";
import { SeverityGlyph } from "@/ui/indicators";
import { useStatusHintStore } from "../status-hint-store";
import { modeHref, useActiveMode, useViewQuery } from "../orientation/modes";
import { countRu } from "../orientation/plural";
import { newEventsPhrase } from "../queue/queue-copy";
import { useQueue } from "../queue/use-queue";
import { CoordinateFormatSeg, CoordinateText, ScaleText, ZoomText } from "./coord-readout";
import { SourcesItem } from "./sources";
import { StatusPopover } from "./status-popover";

const DEFAULT_HINT = "Колесо — масштаб · перетаскивание — сдвиг";

function Cell({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "flex h-full shrink-0 items-center gap-1.5 border-r border-line-hairline px-1.5 whitespace-nowrap",
        className,
      )}
    >
      {children}
    </div>
  );
}

function ApiItems() {
  const status = useApiStatus();
  const capabilities = useCapabilitySummary();
  const details = <SystemDetails status={status} />;
  return (
    <>
      <Cell className="px-0">
        <StatusPopover
          title="Сервер и модули анализа"
          trigger={
            <ApiStatusLabel
              status={status}
              versionClassName="hidden min-[1600px]:inline"
              detailClassName="hidden min-[1600px]:inline"
            />
          }
        >
          {details}
        </StatusPopover>
      </Cell>
      <Cell className="hidden px-0 lg:flex">
        <StatusPopover
          title="Сервер и модули анализа"
          triggerLabel={`Модули анализа: подключено ${capabilities.availableCount} из ${capabilities.total}`}
          trigger={
            <span>
              Модули{" "}
              <span className="font-mono text-text-primary">
                {capabilities.status === "ready" ? capabilities.availableCount : "—"} /{" "}
                {capabilities.total}
              </span>
            </span>
          }
        >
          {details}
        </StatusPopover>
      </Cell>
    </>
  );
}

function QueueItem() {
  const queue = useQueue();
  const mode = useActiveMode();
  const router = useRouter();
  const query = useViewQuery();
  const setQueueOpen = useShellUiStore((state) => state.setQueueOpen);
  if (queue.newCount === 0 || !mode) return null;

  const openQueue = () => {
    if (mode.id !== "models") {
      setQueueOpen(mode.id, true);
      return;
    }
    setQueueOpen("monitor", true);
    router.push(modeHref(WORKSPACE_MODES[0], query));
  };

  return (
    <Cell className="hidden px-0 lg:flex">
      <button
        type="button"
        onClick={openQueue}
        aria-label={`Очередь: ${newEventsPhrase(queue.newCount)}${queue.newIncludesDemo ? ", есть ДЕМО" : ""}. Открыть`}
        className="flex h-full items-center gap-1.5 px-1.5 hover:bg-surface-raised hover:text-text-primary"
      >
        {queue.worstNew ? <SeverityGlyph severity={queue.worstNew} size={12} /> : null}
        <span
          className={cn(
            queue.worstNew === "alarm" && "text-state-alarm",
            queue.worstNew === "caution" && "text-state-caution",
          )}
        >
          Очередь <span className="font-mono">{queue.newCount}</span> нов.
        </span>
        {queue.newIncludesDemo ? <DemoTag /> : null}
      </button>
    </Cell>
  );
}

function DemoItem() {
  const enabled = useWorkspaceStore((state) => state.demoFixtures);
  const candidates = useCandidates();
  if (!enabled) return <Cell className="text-text-tertiary">Фикстуры скрыты</Cell>;
  return (
    <Cell>
      <DemoTag />
      {candidates.origin === "none" ? (
        <span>в этом районе фикстур нет</span>
      ) : (
        <span>
          {countRu(candidates.data.length, ["кандидат", "кандидата", "кандидатов"])}
          <span className="hidden xl:inline"> из фикстуры</span>
        </span>
      )}
    </Cell>
  );
}

function HintItem() {
  const hint = useStatusHintStore((state) => state.hint);
  return (
    <div
      className="hidden h-full min-w-0 flex-1 items-center overflow-hidden border-r border-line-hairline px-1.5 whitespace-nowrap text-text-tertiary 2xl:flex"
      aria-live="polite"
    >
      <span className="truncate">{hint ?? DEFAULT_HINT}</span>
    </div>
  );
}

function KeysItem() {
  const open = useShellUiStore((state) => state.setShortcutSheetOpen);
  return (
    <button
      type="button"
      onClick={() => open(true)}
      aria-keyshortcuts="Shift+Slash"
      className="hidden h-full shrink-0 items-center gap-1 px-1.5 hover:bg-surface-raised hover:text-text-primary lg:flex"
    >
      <span className="font-mono text-text-primary">?</span> Клавиши
    </button>
  );
}

export function StatusBar() {
  return (
    <footer className="flex h-full min-w-0 items-stretch border-t border-line-hairline bg-surface-panel text-[11px] text-text-secondary [font-stretch:88%]">
      <ApiItems />
      <QueueItem />
      <DemoItem />
      <HintItem />
      <Cell className="ml-auto 2xl:ml-0">
        <CoordinateText />
        <span className="hidden xl:inline-flex">
          <CoordinateFormatSeg />
        </span>
      </Cell>
      <Cell className="gap-2">
        <ScaleText />
        <span className="hidden lg:inline">
          <ZoomText />
        </span>
      </Cell>
      <Cell className="hidden text-text-tertiary min-[1600px]:flex">EPSG:3857</Cell>
      <Cell className="hidden px-0 lg:flex">
        <SourcesItem />
      </Cell>
      <KeysItem />
    </footer>
  );
}
